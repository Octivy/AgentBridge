"""Asynchronous agent task orchestration for the panel.

The panel's "给智能体下命令" flow needs three things the synchronous
``run_host_task`` cannot provide:

1. **Non-blocking start** — ``POST /agent/task`` returns the task id at once
   (no 90s synchronous wait); the loop runs as an asyncio task.
2. **Visible progress** — every loop step is serialized into the task record
   as it happens, so the panel can poll and render thinking/tool activity.
3. **Write confirmation (annotate)** — when a write tool is requested the
   task stops at ``needs_confirmation`` with a ``pending_write``. The panel
   shows the call; approve executes it (dry-run -> ticket -> commit) and
   continues the loop, reject feeds the refusal back to the model. Every
   subsequent write stops for confirmation again.

State lives in :class:`agent.task_store.AgentTaskStore` and survives restarts.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Sequence

from agent.host_task import (
    AgentTaskRequest,
    CombinedToolExecutor,
    TaskContext,
    build_task_context,
    confirm_policy,
    record_task_handoff,
    serialize_executed,
    serialize_step,
)
from agent.loop import AgentLoop
from agent.task_store import AgentTaskRecord, AgentTaskStore, agent_task_store
from agent.tools import tool_result_message
from cadmcp.tool_executor import CadToolExecutor
from cadmcp.tool_registry import ToolDefinition
from delivery.service import DeliveryService, delivery_service
from host_mcp.runtime import HostMcpExecutor

NO_TOOLS_MESSAGE = "没有可用的宿主工具，请先在配置中心确认软件桥在线。"
RESULT_TEXT_LIMIT = 800
REJECTED_WRITE_MESSAGE = (
    "用户拒绝了这次写操作。不要重试同一个写操作；"
    "请总结当前已完成的内容，或改用只读工具继续。"
)


class AgentTaskRunner:
    """Start, track and confirm panel agent tasks."""

    def __init__(
        self,
        store: Optional[AgentTaskStore] = None,
        delivery: Optional[DeliveryService] = None,
        *,
        host_executor: Optional[HostMcpExecutor] = None,
        cad_executor: Optional[CadToolExecutor] = None,
        cad_tools: Optional[List[ToolDefinition]] = None,
        provider: Optional[Any] = None,
    ) -> None:
        self._store = store or agent_task_store
        self._delivery = delivery or delivery_service
        # Optional injections (tests / advanced embedding). When set they are
        # used for both start and confirm-resume so the whole lifecycle stays
        # on the same fakes.
        self._host_executor = host_executor
        self._cad_executor = cad_executor
        self._cad_tools = cad_tools
        self._provider = provider
        self._running: Dict[str, asyncio.Task] = {}

    # ----- public API -----

    async def start_task(self, request: AgentTaskRequest) -> Dict[str, Any]:
        message = (request.message or "").strip()
        if not message:
            raise ValueError("message is required")

        task_id = (request.task_id or "").strip() or str(uuid.uuid4())
        request = request.model_copy(update={"task_id": task_id, "message": message})

        record = AgentTaskRecord(
            task_id=task_id,
            user_goal=message,
            approval=request.approval,
            tool_scope=request.tool_scope,
            max_iterations=request.max_iterations,
        )

        context = self._build_context(request)
        if context is None:
            record.status = "no_tools"
            record.stopped_reason = "no_tools"
            record.final_text = NO_TOOLS_MESSAGE
            self._save(record)
            return record.view()

        record.protocol = context.protocol
        self._save(record)
        history: List[Dict[str, Any]] = [{"role": "user", "content": message}]
        self._spawn(task_id, self._guarded_run(task_id, context, history))
        current = self._store.get(task_id)
        return current.view() if current is not None else record.view()

    async def confirm_task(self, task_id: str, approve: bool) -> Dict[str, Any]:
        record = self._store.get(task_id)
        if record is None:
            raise KeyError(task_id)
        if record.status != "needs_confirmation" or not record.pending_write:
            raise ValueError(f"task {task_id} is not awaiting confirmation")

        pending = dict(record.pending_write)
        record.pending_write = None
        record.status = "running"
        self._save(record)

        # Approved writes must be able to commit (dry-run -> ticket -> apply),
        # so the resumed executor runs with full approval; the loop gate below
        # still stops every *new* write for the next confirmation.
        resume_request = AgentTaskRequest(
            message=record.user_goal,
            approval="full",
            tool_scope=record.tool_scope,
            task_id=task_id,
            max_iterations=record.max_iterations,
        )
        context = self._build_context(resume_request)
        if context is None:
            record.status = "failed"
            record.error = NO_TOOLS_MESSAGE
            self._save(record)
            return record.view()

        history = list(record.history)
        call_id = str(pending.get("id") or "")
        if approve:
            result_text, ok, error_code = await self._execute_pending(context, pending)
            record.executed_tools.append(
                {
                    "name": str(pending.get("name") or ""),
                    "ok": ok,
                    "error_code": error_code,
                    "result_text": result_text[:RESULT_TEXT_LIMIT],
                }
            )
            history.append(tool_result_message(context.protocol, call_id, result_text, is_error=not ok))
        else:
            history.append(
                tool_result_message(context.protocol, call_id, REJECTED_WRITE_MESSAGE, is_error=True)
            )

        self._spawn(task_id, self._guarded_run(task_id, context, history))
        current = self._store.get(task_id)
        return current.view() if current is not None else record.view()

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        record = self._store.get(task_id)
        return record.view() if record is not None else None

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [record.view() for record in self._store.list(limit)]

    async def wait_until_settled(self, task_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Test helper: poll until the task leaves running/needs-confirmation."""

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            record = self._store.get(task_id)
            if record is not None and record.status in {"completed", "failed", "no_tools"}:
                return record.view()
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"task {task_id} did not settle within {timeout}s")
            await asyncio.sleep(0.01)

    # ----- internals -----

    def _build_context(self, request: AgentTaskRequest) -> Optional[TaskContext]:
        return build_task_context(
            request,
            executor=self._host_executor,
            cad_executor=self._cad_executor,
            cad_tools=self._cad_tools,
            provider=self._provider,
        )

    def _save(self, record: AgentTaskRecord) -> None:
        self._store.touch(record)
        self._store.upsert(record)

    def _spawn(self, task_id: str, coro) -> None:
        handle = asyncio.create_task(coro)
        self._running[task_id] = handle

        def _discard(done: asyncio.Task) -> None:
            self._running.pop(task_id, None)
            if not done.cancelled() and done.exception() is not None:
                # _guarded_run should have captured it; keep a hard failure visible.
                record = self._store.get(task_id)
                if record is not None and record.status == "running":
                    record.status = "failed"
                    record.error = str(done.exception())
                    self._save(record)

        handle.add_done_callback(_discard)

    async def _execute_pending(self, context: TaskContext, pending: Dict[str, Any]):
        name = str(pending.get("name") or "")
        arguments = dict(pending.get("arguments") or {})
        try:
            result_text = await context.tool_executor(name, arguments)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as a tool error
            return f"ERROR: {exc}", False, "execution_error"
        ok = True
        error_code = ""
        try:
            payload = json.loads(result_text)
            if isinstance(payload, dict) and "ok" in payload:
                ok = bool(payload["ok"])
                error_code = str(payload.get("error_code") or "")
        except (ValueError, TypeError):
            pass
        return result_text, ok, error_code

    async def _guarded_run(self, task_id: str, context: TaskContext, history: Sequence[Dict[str, Any]]) -> None:
        record = self._store.get(task_id)
        if record is None:
            return
        try:
            await self._run_segment(record, context, list(history))
        except Exception as exc:  # noqa: BLE001 - task-level failure is a state, not a crash
            record.status = "failed"
            record.error = str(exc)
            self._save(record)

    async def _run_segment(self, record: AgentTaskRecord, context: TaskContext, history: List[Dict[str, Any]]) -> None:
        budget = record.remaining_iterations()
        if budget <= 0:
            record.status = "completed"
            record.stopped_reason = "max_iterations"
            record_task_handoff(self._delivery, record.task_id, record.user_goal, record.executed_tools)
            self._save(record)
            return

        record.status = "running"
        self._save(record)
        base_index = len(record.steps)

        async def on_step(step) -> None:
            record.steps.append(serialize_step(step, base_index + step.index, RESULT_TEXT_LIMIT))
            for item in step.executed_tools:
                record.executed_tools.append(serialize_executed(item, RESULT_TEXT_LIMIT))
            self._save(record)

        loop = AgentLoop(
            provider=context.provider,
            tools=context.tools,
            execute_tool=context.tool_executor,
            confirm_write=confirm_policy(record.approval),
            max_iterations=budget,
            on_step=on_step,
        )
        result = await loop.run(history)
        record.iterations += result.iterations
        record.history = list(result.history)

        if result.stopped_reason == "needs_confirmation":
            # Enrich first, then flip status: the dry-run await must not expose
            # an intermediate state (status set, pending_write still None).
            pending = dict(result.pending_write or {})
            pending = await self._enrich_pending_preview(context, pending)
            record.pending_write = pending
            record.status = "needs_confirmation"
            record.stopped_reason = "needs_confirmation"
        else:
            record.status = "completed"
            record.stopped_reason = result.stopped_reason
            record.final_text = result.final_text
            record.pending_write = None
            record_task_handoff(self._delivery, record.task_id, record.user_goal, record.executed_tools)
        self._save(record)

    async def _enrich_pending_preview(self, context: TaskContext, pending: Dict[str, Any]) -> Dict[str, Any]:
        """Attach a dry-run preview to a blocked write so the panel can show
        what the operation will change before the user confirms.

        Write tools run through dry-run (host: no permission token -> preview;
        CAD: default dry_run=True) without committing, so this is side-effect
        free. Failures degrade silently — the card falls back to raw args.
        """

        name = str(pending.get("name") or "")
        tool = next((item for item in context.tools if item.tool_name == name), None)
        if tool is None:
            return pending
        risk = (tool.risk_level or "").strip().lower()
        if risk in {"read_only", "preview_only"} or not tool.dry_run_supported:
            return pending

        # Never reuse the loop's executor here: a resume context runs with
        # full approval and would auto-commit. Preview must stay a dry-run.
        preview_executor = CombinedToolExecutor(
            host_executor=context.host_executor,
            cad_executor=context.cad_executor,
            host_tools=context.host_tools,
            cad_tools=context.cad_tools,
            approval="annotate",
            trace_id="",
        )
        try:
            result_text = await preview_executor(name, dict(pending.get("arguments") or {}))
        except Exception:  # noqa: BLE001 - preview is best-effort
            return pending
        try:
            payload = json.loads(result_text)
        except (ValueError, TypeError):
            return pending
        if not isinstance(payload, dict):
            return pending

        preview = _extract_dry_run_preview(payload)
        if preview is not None:
            pending["preview"] = preview
        return pending


def _extract_dry_run_preview(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pick the human-relevant bits out of a dry-run result payload."""

    data = payload.get("data") or payload.get("result") or payload.get("preview")
    summary = str(payload.get("summary") or "").strip()
    if not summary and not isinstance(data, (dict, list)):
        # e.g. permission_required errors or empty previews carry nothing to show
        return None
    return {
        "dry_run": bool(payload.get("dry_run", False)),
        "requires_permission": bool(payload.get("requires_permission", False)),
        "summary": summary[:400],
        "data": data if isinstance(data, (dict, list)) else None,
    }


agent_task_runner = AgentTaskRunner()


__all__ = ["AgentTaskRunner", "agent_task_runner"]
