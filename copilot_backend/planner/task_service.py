from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import uuid

from harness.events import HarnessEventType, make_harness_event
from planner.memory_store import InMemoryPlannerStore
from planner.session import PlannerExecutionEventRecord, PlannerSession, PlannerSessionState, PlannerTaskErrorRecord, PlannerTaskStatus


@dataclass
class PlannerTaskSummary:
    task_id: str
    user_goal: str
    task_status: str
    trace_id: str = ""
    last_user_message: str = ""
    active_step: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resumable: bool = False
    retryable: bool = False
    cancellable: bool = False
    last_error: Optional[PlannerTaskErrorRecord] = None


class PlannerTaskService:
    """Thin task-management facade over the current in-memory Planner store.

    This service does not replace PlannerSession yet. It isolates task/session
    lifecycle decisions so the runtime and HTTP handlers do not need to keep
    owning task creation, resume gating, and future task operations directly.
    """

    def __init__(self, *, store: Optional[InMemoryPlannerStore] = None) -> None:
        self._store = store or InMemoryPlannerStore()

    def resolve_session(self, planner_session_id: Optional[str], user_message: str, trace_id: Optional[str] = None) -> PlannerSession:
        session_id = (planner_session_id or "").strip()
        normalized_trace_id = (trace_id or "").strip()
        if session_id:
            existing = self._store.get(session_id)
            if existing is not None and existing.state.task_status not in {
                PlannerTaskStatus.COMPLETED,
                PlannerTaskStatus.FAILED,
                PlannerTaskStatus.CANCELLED,
            }:
                if normalized_trace_id and not existing.state.trace_id:
                    existing.state.trace_id = normalized_trace_id
                return existing

        return self.create_task(user_goal=user_message or "执行 CAD 智能体任务", last_user_message=user_message, trace_id=normalized_trace_id)

    def create_task(self, *, user_goal: str, last_user_message: str = "", mode: str = "agent", trace_id: str = "") -> PlannerSession:
        state = PlannerSessionState(
            session_id=str(uuid.uuid4()),
            user_goal=user_goal,
            mode=mode,
            trace_id=trace_id or str(uuid.uuid4()),
            last_user_message=last_user_message,
        )
        return self._store.create(state)

    def get_task(self, task_id: str) -> Optional[PlannerSession]:
        return self._store.get(task_id)

    def save_task(self, session: PlannerSession) -> PlannerSession:
        return self._store.save(session)

    def cancel_task(self, task_id: str, reason: str = "任务已取消。") -> Optional[PlannerSession]:
        session = self._store.get(task_id)
        if session is None:
            return None

        session.cancel(reason)
        return self._store.save(session)

    def resume_task(self, task_id: str, user_message: str) -> Optional[PlannerSession]:
        session = self._store.get(task_id)
        if session is None:
            return None
        if session.state.task_status != PlannerTaskStatus.WAITING_USER:
            return None

        session.prepare_resume(user_message)
        return self._store.save(session)

    def retry_task(self, task_id: str) -> Optional[PlannerSession]:
        session = self._store.get(task_id)
        if session is None:
            return None
        if session.state.task_status != PlannerTaskStatus.FAILED:
            return None

        session.prepare_retry()
        return self._store.save(session)

    def record_local_result(
        self,
        task_id: str,
        *,
        status: str,
        message: str = "",
        affected_entities_count: int = 0,
        trace_id: str = "",
        tool_name: str = "local_apply_preview",
        details: Optional[dict] = None,
    ) -> Optional[PlannerSession]:
        session = self._store.get(task_id)
        if session is None:
            return None

        normalized_status = (status or "completed").strip().lower()
        normalized_tool_name = (tool_name or "local_apply_preview").strip() or "local_apply_preview"
        normalized_trace_id = (trace_id or session.state.trace_id or "").strip()
        event_details = dict(details or {})
        event_details.setdefault("dry_run", False)
        event_details.setdefault("affected_entities_count", max(affected_entities_count, 0))
        event_details.setdefault(
            "audit",
            {
                "task_id": session.state.session_id,
                "trace_id": normalized_trace_id,
                "tool_name": normalized_tool_name,
                "side_effect_level": "high",
                "dry_run": False,
                "confirmation_required": False,
                "confirmed_by_local_user": True,
                "write_actor": "local_autocad_plugin",
            },
        )

        session.state.execution_events.append(
            PlannerExecutionEventRecord(
                tool_name=normalized_tool_name,
                status="failed" if normalized_status == "failed" else "succeeded",
                summary=message or ("Local CAD write failed." if normalized_status == "failed" else "Local CAD write completed."),
                trace_id=normalized_trace_id,
                details=event_details,
            )
        )
        if normalized_status != "failed":
            self._append_local_write_harness_events(
                session,
                tool_name=normalized_tool_name,
                message=message,
                trace_id=normalized_trace_id,
                details=event_details,
            )
        if normalized_trace_id and not session.state.trace_id:
            session.state.trace_id = normalized_trace_id

        for step in list(session.state.pending_steps):
            if step and step not in session.state.completed_steps:
                session.state.completed_steps.append(step)
        session.state.pending_steps.clear()

        if normalized_status == "failed":
            session.fail(message or "Local CAD write failed.", error_code="local_cad_write_failed")
        else:
            session.complete(message or "Local CAD write completed.")

        return self._store.save(session)

    @staticmethod
    def _append_local_write_harness_events(
        session: PlannerSession,
        *,
        tool_name: str,
        message: str,
        trace_id: str,
        details: dict,
    ) -> None:
        transaction = details.get("transaction") if isinstance(details.get("transaction"), dict) else {}
        affected_entities = details.get("affected_entities") if isinstance(details.get("affected_entities"), list) else []
        affected_entities_count = details.get("affected_entities_count")
        if not isinstance(affected_entities_count, int):
            affected_entities_count = len(affected_entities)

        session.append_harness_event(
            make_harness_event(
                session_id=session.state.session_id,
                task_id=session.state.session_id,
                event_type=HarnessEventType.CAD_TRANSACTION_STARTED,
                sequence=session.next_harness_event_sequence(),
                summary="Local CAD write transaction started.",
                payload={
                    "tool_name": tool_name,
                    "transaction": dict(transaction),
                },
                collapse_default=True,
                trace_id=trace_id,
            )
        )
        session.append_harness_event(
            make_harness_event(
                session_id=session.state.session_id,
                task_id=session.state.session_id,
                event_type=HarnessEventType.CAD_WRITE_APPLIED,
                sequence=session.next_harness_event_sequence(),
                summary=message or "Local CAD write applied.",
                payload={
                    "tool_name": tool_name,
                    "transaction": dict(transaction),
                    "affected_entities_count": max(affected_entities_count, 0),
                    "affected_entities": list(affected_entities),
                },
                collapse_default=False,
                trace_id=trace_id,
            )
        )

    def record_permission_decision(
        self,
        task_id: str,
        *,
        decision: str,
        message: str = "",
        trace_id: str = "",
        details: Optional[dict] = None,
    ) -> Optional[PlannerSession]:
        session = self._store.get(task_id)
        if session is None:
            return None

        normalized_decision = (decision or "").strip().lower() or "deny"
        normalized_trace_id = (trace_id or session.state.trace_id or "").strip()
        event_details = dict(details or {})
        event_details.setdefault("decision", normalized_decision)
        event_details.setdefault("message", message or "")
        event_details.setdefault(
            "audit",
            {
                "task_id": session.state.session_id,
                "trace_id": normalized_trace_id,
                "tool_name": "permission_decision",
                "side_effect_level": "high",
                "dry_run": True,
                "confirmation_required": True,
                "confirmed_by_local_user": normalized_decision in {"allow", "approve", "confirm"},
                "agent_approval": session.state.agent_approval,
                "approved_by_policy": False,
                "write_actor": "local_autocad_plugin",
            },
        )

        status = "cancelled" if normalized_decision in {"deny", "reject", "cancel"} else "succeeded"
        session.state.execution_events.append(
            PlannerExecutionEventRecord(
                tool_name="permission_decision",
                status=status,
                summary=message or ("Permission denied by user." if status == "cancelled" else "Permission decision recorded."),
                trace_id=normalized_trace_id,
                details=event_details,
            )
        )
        if normalized_trace_id and not session.state.trace_id:
            session.state.trace_id = normalized_trace_id

        if normalized_decision in {"deny", "reject", "cancel"}:
            session.cancel(message or "User denied writing changes to the drawing.")
        else:
            session.wait_for_user(message or "Permission decision recorded.")

        return self._store.save(session)

    def list_recent_tasks(self, limit: int = 10, status_filter: Optional[str] = None) -> List[PlannerTaskSummary]:
        sessions = sorted(
            self._store.list_sessions(),
            key=lambda session: session.state.updated_at,
            reverse=True,
        )
        normalized_status = self.normalize_status_filter(status_filter)
        if normalized_status is not None:
            sessions = [
                session
                for session in sessions
                if self.matches_status_filter(session, normalized_status)
            ]
        recent_sessions = sessions[: max(limit, 0)]
        return [
            PlannerTaskSummary(
                task_id=session.state.session_id,
                trace_id=session.state.trace_id,
                user_goal=session.state.user_goal,
                task_status=session.state.task_status.value,
                last_user_message=session.state.last_user_message,
                active_step=session.active_step(),
                created_at=session.state.created_at,
                updated_at=session.state.updated_at,
                resumable=self.is_resumable(session),
                retryable=self.is_retryable(session),
                cancellable=self.is_cancellable(session),
                last_error=session.state.last_error,
            )
            for session in recent_sessions
        ]

    @staticmethod
    def is_resumable(session: PlannerSession) -> bool:
        return session.state.task_status == PlannerTaskStatus.WAITING_USER

    @staticmethod
    def is_retryable(session: PlannerSession) -> bool:
        return session.state.task_status == PlannerTaskStatus.FAILED

    @staticmethod
    def is_cancellable(session: PlannerSession) -> bool:
        return session.state.task_status in {
            PlannerTaskStatus.CREATED,
            PlannerTaskStatus.RUNNING,
            PlannerTaskStatus.WAITING_USER,
        }

    @staticmethod
    def normalize_status_filter(status_filter: Optional[str]) -> Optional[str]:
        value = (status_filter or "").strip().lower()
        if not value or value == "all":
            return None
        return value

    @staticmethod
    def matches_status_filter(session: PlannerSession, status_filter: str) -> bool:
        if status_filter == "active":
            return session.state.task_status in {
                PlannerTaskStatus.CREATED,
                PlannerTaskStatus.RUNNING,
                PlannerTaskStatus.WAITING_USER,
            }

        return session.state.task_status.value == status_filter
