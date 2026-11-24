from __future__ import annotations

from typing import Any

from harness.events import HarnessEvent, HarnessEventType, make_harness_event


def map_execution_event_to_harness_event(
    *,
    session_id: str,
    task_id: str,
    sequence: int,
    execution_event: dict[str, Any],
    trace_id: str = "",
) -> HarnessEvent:
    status = str(execution_event.get("status") or "").strip().lower()
    event_type = HarnessEventType.TOOL_RESULT
    if status in {"failed", "error"}:
        event_type = HarnessEventType.TASK_FAILED

    tool_name = str(execution_event.get("tool_name") or "").strip()
    summary = str(execution_event.get("summary") or tool_name or "Tool result").strip()
    return make_harness_event(
        session_id=session_id,
        task_id=task_id,
        event_type=event_type,
        sequence=sequence,
        summary=summary,
        payload={
            "source": "legacy_execution_event",
            "tool_name": tool_name,
            "status": status,
            "request_id": execution_event.get("request_id"),
            "details": execution_event.get("details") or {},
        },
        collapse_default=True,
        trace_id=trace_id or str(execution_event.get("trace_id") or ""),
    )
