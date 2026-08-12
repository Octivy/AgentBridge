from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class HarnessEventType(str, Enum):
    SESSION_CREATED = "session_created"
    USER_MESSAGE_RECEIVED = "user_message_received"
    CONTEXT_CAPTURE_STARTED = "context_capture_started"
    CONTEXT_CAPTURE_COMPLETED = "context_capture_completed"
    THINKING_STARTED = "thinking_started"
    THINKING_DELTA = "thinking_delta"
    THINKING_COMPLETED = "thinking_completed"
    PLAN_CREATED = "plan_created"
    PLAN_REVISED = "plan_revised"
    STEP_STARTED = "step_started"
    TOOL_REQUESTED = "tool_requested"
    TOOL_VALIDATED = "tool_validated"
    PERMISSION_REQUESTED = "permission_requested"
    PERMISSION_DECISION = "permission_decision"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_RESULT = "tool_result"
    DRY_RUN_PREVIEW_CREATED = "dry_run_preview_created"
    CAD_TRANSACTION_STARTED = "cad_transaction_started"
    CAD_WRITE_APPLIED = "cad_write_applied"
    SEMANTIC_GRAPH_UPDATED = "semantic_graph_updated"
    TASK_PATCH_CREATED = "task_patch_created"
    VERSION_SNAPSHOT_CREATED = "version_snapshot_created"
    STEP_COMPLETED = "step_completed"
    ASSISTANT_MESSAGE_CREATED = "assistant_message_created"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_RESUMED = "task_resumed"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HarnessEvent:
    event_id: str
    session_id: str
    task_id: str
    event_type: HarnessEventType
    sequence: int
    timestamp: str
    summary: str = ""
    step_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    visible_to_user: bool = True
    collapse_default: bool = False
    trace_id: str = ""


def make_harness_event(
    *,
    session_id: str,
    task_id: str,
    event_type: HarnessEventType,
    sequence: int,
    summary: str = "",
    step_id: str = "",
    payload: dict[str, Any] | None = None,
    visible_to_user: bool = True,
    collapse_default: bool = False,
    trace_id: str = "",
) -> HarnessEvent:
    return HarnessEvent(
        event_id=f"evt_{uuid4().hex}",
        session_id=session_id,
        task_id=task_id,
        event_type=event_type,
        sequence=sequence,
        timestamp=utc_now_iso(),
        summary=summary,
        step_id=step_id,
        payload=dict(payload or {}),
        visible_to_user=visible_to_user,
        collapse_default=collapse_default,
        trace_id=trace_id,
    )
