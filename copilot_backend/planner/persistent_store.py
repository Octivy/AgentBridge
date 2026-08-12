import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from harness.events import HarnessEvent, HarnessEventType
from planner.memory_store import InMemoryPlannerStore
from planner.session import (
    PlannerActionType,
    PlannerDecision,
    PlannerExecutionEventRecord,
    PlannerObservation,
    PlannerSession,
    PlannerSessionState,
    PlannerTaskErrorRecord,
    PlannerTaskStatus,
    ToolCallSpec,
)


class JsonPlannerStore(InMemoryPlannerStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)
        self._load()

    def create(self, state: PlannerSessionState) -> PlannerSession:
        session = super().create(state)
        self._persist()
        return session

    def save(self, session: PlannerSession) -> PlannerSession:
        saved = super().save(session)
        self._persist()
        return saved

    def delete(self, session_id: str) -> None:
        super().delete(session_id)
        self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return

        try:
            raw_items = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(raw_items, list):
            return

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            state = _state_from_dict(item)
            self._sessions[state.session_id] = PlannerSession(state)

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_to_jsonable(session.state) for session in self.list_sessions()]
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self._path)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _state_from_dict(data: dict[str, Any]) -> PlannerSessionState:
    return PlannerSessionState(
        session_id=str(data.get("session_id") or ""),
        user_goal=str(data.get("user_goal") or ""),
        mode=str(data.get("mode") or "agent"),
        trace_id=str(data.get("trace_id") or ""),
        task_status=_task_status(data.get("task_status")),
        created_at=_datetime(data.get("created_at")),
        updated_at=_datetime(data.get("updated_at")),
        current_iteration=int(data.get("current_iteration") or 0),
        max_iterations=int(data.get("max_iterations") or 8),
        context_snapshot=dict(data.get("context_snapshot") or {}),
        memory=[_observation(item) for item in data.get("memory") or [] if isinstance(item, dict)],
        pending_steps=[str(item) for item in data.get("pending_steps") or []],
        completed_steps=[str(item) for item in data.get("completed_steps") or []],
        selected_skills=[str(item) for item in data.get("selected_skills") or []],
        pending_confirmation_tool_calls=[_tool_call(item) for item in data.get("pending_confirmation_tool_calls") or [] if isinstance(item, dict)],
        execution_events=[_execution_event(item) for item in data.get("execution_events") or [] if isinstance(item, dict)],
        harness_events=[_harness_event(item) for item in data.get("harness_events") or [] if isinstance(item, dict)],
        last_user_message=str(data.get("last_user_message") or ""),
        last_model_decision=_decision(data.get("last_model_decision")),
        last_tool_results=[_observation(item) for item in data.get("last_tool_results") or [] if isinstance(item, dict)],
        final_response=str(data.get("final_response") or ""),
        last_error=_error(data.get("last_error")),
    )


def _task_status(value: Any) -> PlannerTaskStatus:
    try:
        return PlannerTaskStatus(str(value or PlannerTaskStatus.CREATED.value))
    except ValueError:
        return PlannerTaskStatus.CREATED


def _action_type(value: Any) -> PlannerActionType:
    try:
        return PlannerActionType(str(value or PlannerActionType.RESPOND.value))
    except ValueError:
        return PlannerActionType.RESPOND


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    from planner.session import utc_now

    return utc_now()


def _observation(data: dict[str, Any]) -> PlannerObservation:
    return PlannerObservation(
        source=str(data.get("source") or ""),
        payload=dict(data.get("payload") or {}),
        is_error=bool(data.get("is_error", False)),
    )


def _tool_call(data: dict[str, Any]) -> ToolCallSpec:
    return ToolCallSpec(
        tool_name=str(data.get("tool_name") or ""),
        arguments=dict(data.get("arguments") or {}),
    )


def _decision(data: Any) -> PlannerDecision | None:
    if not isinstance(data, dict):
        return None
    return PlannerDecision(
        intent=str(data.get("intent") or ""),
        reasoning_summary=str(data.get("reasoning_summary") or ""),
        next_action=_action_type(data.get("next_action")),
        tool_calls=[_tool_call(item) for item in data.get("tool_calls") or [] if isinstance(item, dict)],
        selected_skills=[str(item) for item in data.get("selected_skills") or []],
        completion_check=bool(data.get("completion_check", False)),
        user_message=str(data.get("user_message") or ""),
        ask_user_type=str(data.get("ask_user_type") or ""),
        ask_user_hint=str(data.get("ask_user_hint") or ""),
        suggested_steps=[str(item) for item in data.get("suggested_steps") or []],
    )


def _execution_event(data: dict[str, Any]) -> PlannerExecutionEventRecord:
    return PlannerExecutionEventRecord(
        tool_name=str(data.get("tool_name") or ""),
        status=str(data.get("status") or ""),
        summary=str(data.get("summary") or ""),
        request_id=str(data.get("request_id") or ""),
        trace_id=str(data.get("trace_id") or ""),
        error_code=str(data.get("error_code") or ""),
        details=dict(data.get("details") or {}),
    )


def _harness_event(data: dict[str, Any]) -> HarnessEvent:
    event_type_raw = str(data.get("event_type") or HarnessEventType.TOOL_RESULT.value)
    try:
        event_type = HarnessEventType(event_type_raw)
    except ValueError:
        event_type = HarnessEventType.TOOL_RESULT

    return HarnessEvent(
        event_id=str(data.get("event_id") or ""),
        session_id=str(data.get("session_id") or ""),
        task_id=str(data.get("task_id") or ""),
        event_type=event_type,
        sequence=int(data.get("sequence") or 0),
        timestamp=str(data.get("timestamp") or ""),
        summary=str(data.get("summary") or ""),
        step_id=str(data.get("step_id") or ""),
        payload=dict(data.get("payload") or {}),
        visible_to_user=bool(data.get("visible_to_user", True)),
        collapse_default=bool(data.get("collapse_default", False)),
        trace_id=str(data.get("trace_id") or ""),
    )


def _error(data: Any) -> PlannerTaskErrorRecord | None:
    if not isinstance(data, dict):
        return None
    return PlannerTaskErrorRecord(
        code=str(data.get("code") or ""),
        message=str(data.get("message") or ""),
        technical_detail=str(data.get("technical_detail") or ""),
    )
