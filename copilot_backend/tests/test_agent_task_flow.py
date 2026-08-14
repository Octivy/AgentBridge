"""End-to-end lifecycle tests for the panel agent task runner.

Covers the P1 closed-loop behaviors:
- async start with visible step progress;
- annotate mode stops at the first write (needs_confirmation + pending_write);
- confirm(approve) executes the pending write (dry-run -> ticket -> commit)
  and continues; every subsequent write stops again;
- confirm(reject) feeds the refusal back to the model;
- no_tools short-circuit and store hygiene (history stripped, trim).
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.host_task import AgentTaskRequest  # noqa: E402
from agent.task_runner import AgentTaskRunner  # noqa: E402
from agent.task_store import AgentTaskRecord, AgentTaskStore  # noqa: E402
from delivery.service import DeliveryService  # noqa: E402
from delivery.store import DeliveryStore  # noqa: E402
from mcp import types as mcp_types  # noqa: E402


class FakeProvider:
    protocol = "openai_chat"

    def __init__(self, script: List[Dict[str, Any]]) -> None:
        self._script = list(script)
        self.calls = 0
        self.seen: List[List[Dict[str, Any]]] = []

    async def complete(self, messages, tools):
        self.seen.append([dict(item) for item in messages])
        step = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return step


class FakeHostExecutor:
    def __init__(self) -> None:
        self.calls: List = []

    def list_tools(self):
        read = mcp_types.Tool(
            name="blender_scene_summary",
            title="场景摘要",
            description="summary",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            annotations=mcp_types.ToolAnnotations(
                title="s", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
            ),
            _meta={"hostmcp/riskLevel": "read_only", "hostmcp/dryRunSupported": False},
        )
        write = mcp_types.Tool(
            name="blender_create_cube",
            title="创建立方体",
            description="cube",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
            annotations=mcp_types.ToolAnnotations(
                title="c", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
            ),
            _meta={"hostmcp/riskLevel": "high", "hostmcp/dryRunSupported": True},
        )
        return [read, write]

    def execute_tool_sync(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "blender_scene_summary":
            return {"ok": True, "tool_name": name, "data": {"object_count": 3}, "dry_run": False}
        if arguments.get("dry_run", False) is False and arguments.get("permission_token"):
            return {
                "ok": True,
                "tool_name": name,
                "data": {"object_name": "T1"},
                "dry_run": False,
                "rollback_token": "blender-cube-T1",
            }
        return {
            "ok": True,
            "tool_name": name,
            "data": {"preview": {"object_name": "T1"}},
            "dry_run": True,
            "requires_permission": True,
            "permission_token": "ticket-1",
            "preview_hash": "hash-1",
        }


class EmptyExecutor:
    def list_tools(self):
        return []


def make_runner(tmp_path: Path, executor, provider) -> AgentTaskRunner:
    return AgentTaskRunner(
        store=AgentTaskStore(path=tmp_path / "agent_tasks.json"),
        delivery=DeliveryService(store=DeliveryStore(path=tmp_path / "deliveries.json")),
        host_executor=executor,
        provider=provider,
    )


async def wait_status(runner: AgentTaskRunner, task_id: str, statuses, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        view = runner.get(task_id)
        last = view
        if view is not None and view["status"] in statuses:
            if view["status"] == "failed" and "failed" not in statuses:
                raise AssertionError(f"task failed: {view.get('error')}")
            return view
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {statuses}; last={last}")


@pytest.mark.asyncio
async def test_full_approval_completes_with_visible_steps(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider(
        [
            {
                "content": "检查场景",
                "tool_calls": [{"id": "c1", "name": "blender_scene_summary", "arguments": {}}],
            },
            {
                "content": "创建立方体",
                "tool_calls": [{"id": "c2", "name": "blender_create_cube", "arguments": {"name": "T1"}}],
            },
            {"content": "完成", "tool_calls": []},
        ]
    )
    runner = make_runner(tmp_path, executor, provider)

    view = await runner.start_task(AgentTaskRequest(message="查看并创建 T1", approval="full"))
    assert view["status"] in {"running", "completed"}
    assert "history" not in view

    final = await wait_status(runner, view["task_id"], {"completed"})
    assert final["stopped_reason"] == "completed"
    assert final["final_text"] == "完成"
    assert [item["name"] for item in final["executed_tools"]] == [
        "blender_scene_summary",
        "blender_create_cube",
    ]
    assert all(item["ok"] for item in final["executed_tools"])
    assert len(final["steps"]) == 2
    assert final["steps"][0]["executed_tools"][0]["name"] == "blender_scene_summary"

    handoff = runner._delivery.get(view["task_id"])
    assert handoff is not None
    assert handoff.handoff.summary.startswith("Agent 任务完成")


@pytest.mark.asyncio
async def test_annotate_stops_at_write_and_confirm_completes(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider(
        [
            {
                "content": "先看看场景",
                "tool_calls": [{"id": "c1", "name": "blender_scene_summary", "arguments": {}}],
            },
            {
                "content": "准备写入",
                "tool_calls": [{"id": "c2", "name": "blender_create_cube", "arguments": {"name": "T1"}}],
            },
            {"content": "创建完成", "tool_calls": []},
        ]
    )
    runner = make_runner(tmp_path, executor, provider)

    view = await runner.start_task(AgentTaskRequest(message="创建 T1", approval="annotate"))
    blocked = await wait_status(runner, view["task_id"], {"needs_confirmation"})
    assert blocked["pending_write"]["name"] == "blender_create_cube"
    assert blocked["pending_write"]["arguments"] == {"name": "T1"}
    # the read happened, the write did not commit
    assert [item["name"] for item in blocked["executed_tools"]] == ["blender_scene_summary"]
    commits = [
        args
        for name, args in executor.calls
        if name == "blender_create_cube" and args.get("dry_run") is False and args.get("permission_token")
    ]
    assert commits == []

    await runner.confirm_task(blocked["task_id"], approve=True)
    final = await wait_status(runner, blocked["task_id"], {"completed"})
    assert final["final_text"] == "创建完成"
    assert final["pending_write"] is None

    applied = [args for name, args in executor.calls if name == "blender_create_cube"]
    assert any(args.get("dry_run") is False and args.get("permission_token") == "ticket-1" for args in applied)

    handoff = runner._delivery.get(blocked["task_id"])
    assert handoff is not None


@pytest.mark.asyncio
async def test_pending_write_carries_dry_run_preview(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider(
        [
            {
                "content": "准备写入",
                "tool_calls": [{"id": "c1", "name": "blender_create_cube", "arguments": {"name": "T1"}}],
            },
            {"content": "完成", "tool_calls": []},
        ]
    )
    runner = make_runner(tmp_path, executor, provider)

    view = await runner.start_task(AgentTaskRequest(message="创建 T1", approval="annotate"))
    blocked = await wait_status(runner, view["task_id"], {"needs_confirmation"})
    preview = blocked["pending_write"].get("preview")
    assert preview is not None
    assert preview["data"] == {"preview": {"object_name": "T1"}}
    assert preview["requires_permission"] is True
    # a dry-run was performed (no commit): one preview call without a token
    dry_calls = [
        args
        for name, args in executor.calls
        if name == "blender_create_cube" and not args.get("permission_token")
    ]
    assert len(dry_calls) == 1


@pytest.mark.asyncio
async def test_every_subsequent_write_stops_again(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider(
        [
            {
                "content": "第一次写入",
                "tool_calls": [{"id": "c1", "name": "blender_create_cube", "arguments": {"name": "A"}}],
            },
            {
                "content": "第二次写入",
                "tool_calls": [{"id": "c2", "name": "blender_create_cube", "arguments": {"name": "B"}}],
            },
            {"content": "都完成了", "tool_calls": []},
        ]
    )
    runner = make_runner(tmp_path, executor, provider)

    view = await runner.start_task(AgentTaskRequest(message="创建 A 和 B", approval="annotate"))
    first = await wait_status(runner, view["task_id"], {"needs_confirmation"})
    assert first["pending_write"]["arguments"] == {"name": "A"}

    await runner.confirm_task(view["task_id"], approve=True)
    second = await wait_status(runner, view["task_id"], {"needs_confirmation"})
    assert second["pending_write"]["id"] == "c2"
    assert second["pending_write"]["arguments"] == {"name": "B"}

    await runner.confirm_task(view["task_id"], approve=True)
    final = await wait_status(runner, view["task_id"], {"completed"})
    assert final["final_text"] == "都完成了"
    commits = [
        args
        for name, args in executor.calls
        if name == "blender_create_cube" and args.get("permission_token") == "ticket-1"
    ]
    assert len(commits) == 2


@pytest.mark.asyncio
async def test_reject_feeds_refusal_back_to_model(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider(
        [
            {
                "content": "准备写入",
                "tool_calls": [{"id": "c1", "name": "blender_create_cube", "arguments": {"name": "A"}}],
            },
            {"content": "好的，不再写入", "tool_calls": []},
        ]
    )
    runner = make_runner(tmp_path, executor, provider)

    view = await runner.start_task(AgentTaskRequest(message="创建 A", approval="annotate"))
    blocked = await wait_status(runner, view["task_id"], {"needs_confirmation"})

    await runner.confirm_task(blocked["task_id"], approve=False)
    final = await wait_status(runner, blocked["task_id"], {"completed"})
    assert final["final_text"] == "好的，不再写入"
    commits = [
        args
        for name, args in executor.calls
        if name == "blender_create_cube" and args.get("dry_run") is False and args.get("permission_token")
    ]
    assert commits == []

    last_history = provider.seen[-1]
    refusal = [item for item in last_history if str(item.get("content") or "").find("拒绝") >= 0]
    assert refusal, "model must see the refusal before answering"


@pytest.mark.asyncio
async def test_confirm_unknown_task_and_wrong_state(tmp_path):
    executor = FakeHostExecutor()
    provider = FakeProvider([{"content": "完成", "tool_calls": []}])
    runner = make_runner(tmp_path, executor, provider)

    with pytest.raises(KeyError):
        await runner.confirm_task("missing", True)

    view = await runner.start_task(AgentTaskRequest(message="hi", approval="full"))
    final = await wait_status(runner, view["task_id"], {"completed"})
    with pytest.raises(ValueError):
        await runner.confirm_task(final["task_id"], True)


@pytest.mark.asyncio
async def test_no_tools_short_circuits(tmp_path):
    runner = make_runner(tmp_path, EmptyExecutor(), FakeProvider([]))
    view = await runner.start_task(AgentTaskRequest(message="x"))
    assert view["status"] == "no_tools"
    assert "没有可用的宿主工具" in view["final_text"]


@pytest.mark.asyncio
async def test_failed_provider_marks_task_failed(tmp_path):
    executor = FakeHostExecutor()

    class BrokenProvider:
        protocol = "openai_chat"

        async def complete(self, messages, tools):
            raise RuntimeError("model offline")

    runner = make_runner(tmp_path, executor, BrokenProvider())
    view = await runner.start_task(AgentTaskRequest(message="x"))
    failed = await wait_status(runner, view["task_id"], {"failed"})
    assert "model offline" in failed["error"]


def test_store_view_strips_history_and_trims(tmp_path):
    store = AgentTaskStore(path=tmp_path / "agent_tasks.json", max_records=3)
    for index in range(5):
        record = AgentTaskRecord(task_id=f"t-{index}", history=[{"role": "user", "content": "x"}])
        store.touch(record)
        store.upsert(record)
    records = store.list(limit=10)
    assert len(records) == 3
    assert {record.task_id for record in records} == {"t-2", "t-3", "t-4"}
    view = records[0].view()
    assert "history" not in view


def test_store_roundtrip_persists_pending_write(tmp_path):
    path = tmp_path / "agent_tasks.json"
    store = AgentTaskStore(path=path)
    store.upsert(
        AgentTaskRecord(
            task_id="t-1",
            status="needs_confirmation",
            pending_write={"id": "c1", "name": "rhino_create_box", "arguments": {"w": 1}},
            history=[{"role": "user", "content": "build"}],
        )
    )
    reloaded = AgentTaskStore(path=path)
    record = reloaded.get("t-1")
    assert record is not None
    assert record.status == "needs_confirmation"
    assert record.pending_write["name"] == "rhino_create_box"
    assert record.history[0]["content"] == "build"
