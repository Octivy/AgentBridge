import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from host_mcp.runtime import HostMcpExecutor
from host_runtime.registry import HostRegistration, write_registration

from adapters.blender.host import HostAdapter


def _host(host_id: str, host_kind: str, product: str, registry_dir, calls, port: int = 0):
    tools = [
        {
            "tool_name": f"{host_kind}_scene_summary",
            "display_name": "场景摘要",
            "category": "analysis",
            "description": "read-only summary",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "dry_run_supported": False,
            "side_effect_level": "none",
            "result_schema": {"type": "object"},
        },
        {
            "tool_name": f"{host_kind}_create_object",
            "display_name": "创建对象",
            "category": "modeling",
            "description": "write tool with dry-run",
            "input_schema": {
                "type": "object",
                "properties": {"size": {"type": "number"}},
                "additionalProperties": False,
            },
            "dry_run_supported": True,
            "side_effect_level": "high",
            "result_schema": {"type": "object"},
            "rollback_supported": True,
        },
    ]

    def snapshot(scope):
        return {"ok": True, "snapshot": {"schema_version": 1, "source": host_kind, "scope": scope}}

    def execute(tool_name, arguments, dry_run):
        calls.append({"host": host_id, "tool": tool_name, "arguments": arguments, "dry_run": dry_run})
        if tool_name.endswith("_scene_summary"):
            return {"ok": True, "result": {"host": host_id, "count": 1}, "dry_run": False}
        if dry_run:
            return {"ok": True, "result": {"preview": {"size": arguments.get("size")}}, "dry_run": True}
        return {
            "ok": True,
            "result": {"object_id": f"{host_id}-obj-1", "size": arguments.get("size")},
            "dry_run": False,
            "rollback_token": f"rb-{host_id}",
        }

    def rollback(rollback_token):
        return {"ok": True, "result": {"rolled_back": True}}

    adapter = HostAdapter(
        host_id=host_id,
        host_kind=host_kind,
        product=product,
        product_version="1.0",
        tools=tools,
        snapshot_fn=snapshot,
        execute_fn=execute,
        rollback_fn=rollback,
        token=f"token-{host_id}",
        port=port,
    )
    adapter.start()
    registration = HostRegistration(**adapter.registration())
    write_registration(registry_dir, registration)
    return adapter


@pytest.fixture
def two_hosts(tmp_path):
    calls: list = []
    blender = _host("blender-main", "blender", "Blender", tmp_path, calls)
    sketchup = _host("sketchup-main", "sketchup", "SketchUp", tmp_path, calls)
    executor = HostMcpExecutor(registry_dir=tmp_path, refresh_ttl_seconds=30)
    try:
        yield executor, calls, blender, sketchup, tmp_path
    finally:
        blender.stop()
        sketchup.stop()


class TestHostMcpExecutor:
    def test_tools_are_namespaced_and_augmented(self, two_hosts):
        executor, _, _, _, _ = two_hosts
        tools = executor.list_tools()
        names = {tool.name for tool in tools}
        assert names == {
            "blender_scene_summary",
            "blender_create_object",
            "sketchup_scene_summary",
            "sketchup_create_object",
        }
        by_name = {tool.name: tool for tool in tools}
        write_schema = by_name["blender_create_object"].inputSchema
        assert "dry_run" in write_schema["properties"]
        assert "permission_token" in write_schema["properties"]
        assert "trace_id" in write_schema["properties"]
        read_schema = by_name["blender_scene_summary"].inputSchema
        assert "trace_id" in read_schema["properties"]
        assert "permission_token" not in read_schema["properties"]

    def test_read_tool_routes_to_correct_host(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        result = executor.execute_tool_sync("sketchup_scene_summary", {})
        assert result["ok"] is True
        assert result["data"]["host"] == "sketchup-main"
        assert calls == [
            {"host": "sketchup-main", "tool": "sketchup_scene_summary", "arguments": {}, "dry_run": False}
        ]

    def test_write_dry_run_returns_permission_grant(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        result = executor.execute_tool_sync("blender_create_object", {"size": 2.0}, )
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["requires_permission"] is True
        assert result["permission_token"]
        assert result["permission_request_id"]
        assert result["preview_hash"]
        assert calls[0]["dry_run"] is True

    def test_write_without_ticket_is_rejected(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        result = executor.execute_tool_sync("blender_create_object", {"size": 1.0, "dry_run": False})
        assert result["ok"] is False
        assert result["error_code"] == "permission_required"
        assert calls == []

    def test_write_with_ticket_commits(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        preview = executor.execute_tool_sync("blender_create_object", {"size": 3.0})
        commit = executor.execute_tool_sync(
            "blender_create_object",
            {
                "size": 3.0,
                "dry_run": False,
                "permission_token": preview["permission_token"],
                "preview_hash": preview["preview_hash"],
            },
        )
        assert commit["ok"] is True
        assert commit["data"]["object_id"] == "blender-main-obj-1"
        commit_call = calls[-1]
        assert commit_call["dry_run"] is False
        assert commit_call["arguments"]["permission_request_id"] == preview["permission_request_id"]

    def test_write_with_wrong_preview_hash_rejected(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        preview = executor.execute_tool_sync("blender_create_object", {"size": 3.0})
        result = executor.execute_tool_sync(
            "blender_create_object",
            {
                "size": 3.0,
                "dry_run": False,
                "permission_token": preview["permission_token"],
                "preview_hash": "deadbeef",
            },
        )
        assert result["ok"] is False
        assert result["error_code"] == "permission_required"
        assert len(calls) == 1

    def test_ticket_is_single_use(self, two_hosts):
        executor, calls, _, _, _ = two_hosts
        preview = executor.execute_tool_sync("blender_create_object", {"size": 4.0})
        kwargs = {
            "size": 4.0,
            "dry_run": False,
            "permission_token": preview["permission_token"],
            "preview_hash": preview["preview_hash"],
        }
        first = executor.execute_tool_sync("blender_create_object", kwargs)
        second = executor.execute_tool_sync("blender_create_object", kwargs)
        assert first["ok"] is True
        assert second["ok"] is False
        assert second["error_code"] == "permission_required"

    def test_unknown_tool(self, two_hosts):
        executor, _, _, _, _ = two_hosts
        result = executor.execute_tool_sync("ghost_tool", {})
        assert result["ok"] is False
        assert result["error_code"] == "unknown_tool"

    def test_unreachable_host_is_skipped(self, tmp_path):
        calls: list = []
        dead = _host("dead-main", "dead", "Dead", tmp_path, calls, port=0)
        endpoint = dead.endpoint
        dead.stop()
        # rewrite registration to point at the now-closed endpoint
        registration = HostRegistration(
            host_id="dead-main",
            host_kind="dead",
            product="Dead",
            product_version="1.0",
            protocol_version="1.0",
            endpoint=endpoint,
            token="token-dead",
            pid=1,
            registered_at="2026-08-12T00:00:00+00:00",
        )
        write_registration(tmp_path, registration)
        executor = HostMcpExecutor(registry_dir=tmp_path, refresh_ttl_seconds=30, timeout_seconds=2)
        executor.refresh()
        assert executor.tool_names() == []
        assert any(error["host_id"] == "dead-main" for error in executor.errors())

    @pytest.mark.asyncio
    async def test_mcp_stdio_server_discovers_and_calls_host(self, two_hosts):
        _, _, _, _, registry_dir = two_hosts
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "host_mcp", "--transport", "stdio", "--registry-dir", str(registry_dir)],
            env=env,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert "blender_scene_summary" in names
                assert "sketchup_create_object" in names
                result = await session.call_tool("blender_scene_summary", {})
                assert result.isError is False
                assert result.content
