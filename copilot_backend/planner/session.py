from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from harness.events import HarnessEvent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlannerTaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlannerActionType(str, Enum):
    RESPOND = "respond"
    ASK_USER = "ask_user"
    CALL_TOOL = "call_tool"
    FINISH = "finish"


@dataclass
class ToolCallSpec:
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerDecision:
    intent: str
    reasoning_summary: str
    next_action: PlannerActionType
    tool_calls: List[ToolCallSpec] = field(default_factory=list)
    selected_skills: List[str] = field(default_factory=list)
    completion_check: bool = False
    user_message: str = ""
    ask_user_type: str = ""
    ask_user_hint: str = ""
    suggested_steps: List[str] = field(default_factory=list)


@dataclass
class PlannerObservation:
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    is_error: bool = False


@dataclass
class PlannerExecutionEventRecord:
    tool_name: str
    status: str
    summary: str = ""
    request_id: str = ""
    trace_id: str = ""
    error_code: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerTaskErrorRecord:
    code: str
    message: str
    technical_detail: str = ""


@dataclass
class PlannerSessionState:
    session_id: str
    user_goal: str
    mode: str = "agent"
    trace_id: str = ""
    task_status: PlannerTaskStatus = PlannerTaskStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    current_iteration: int = 0
    max_iterations: int = 8
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    agent_approval: str = "annotate"
    memory: List[PlannerObservation] = field(default_factory=list)
    pending_steps: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    selected_skills: List[str] = field(default_factory=list)
    pending_confirmation_tool_calls: List[ToolCallSpec] = field(default_factory=list)
    execution_events: List[PlannerExecutionEventRecord] = field(default_factory=list)
    harness_events: List[HarnessEvent] = field(default_factory=list)
    last_user_message: str = ""
    last_model_decision: Optional[PlannerDecision] = None
    last_tool_results: List[PlannerObservation] = field(default_factory=list)
    final_response: str = ""
    last_error: Optional[PlannerTaskErrorRecord] = None


class PlannerSession:
    """Minimal in-memory Planner session skeleton.

    This class is intentionally lightweight at this stage. It establishes the
    state contract that future agent-mode orchestration will depend on without
    taking over the current runtime flow yet.
    """

    def __init__(self, state: PlannerSessionState) -> None:
        self.state = state

    def mark_running(self) -> None:
        self.state.task_status = PlannerTaskStatus.RUNNING
        self.state.last_error = None
        self._touch()

    def record_observation(self, observation: PlannerObservation) -> None:
        self.state.memory.append(observation)
        if observation.source == "tool":
            self.state.last_tool_results.append(observation)
        self._touch()

    def append_harness_event(self, event: HarnessEvent) -> None:
        self.state.harness_events.append(event)
        self._touch()

    def next_harness_event_sequence(self) -> int:
        return len(self.state.harness_events) + 1

    def apply_decision(self, decision: PlannerDecision) -> None:
        self.state.last_model_decision = decision
        self.state.selected_skills = list(decision.selected_skills)
        self.state.current_iteration += 1
        self._update_steps(decision)
        self._touch()

    def wait_for_user(self, message: str) -> None:
        self.state.task_status = PlannerTaskStatus.WAITING_USER
        self.state.final_response = message
        self.state.last_error = None
        self._touch()

    def wait_for_user_with_hint(self, message: str, *, ask_user_type: str = "", ask_user_hint: str = "") -> None:
        self.state.task_status = PlannerTaskStatus.WAITING_USER
        self.state.final_response = message
        self.state.last_error = None
        if self.state.last_model_decision is not None:
            if ask_user_type:
                self.state.last_model_decision.ask_user_type = ask_user_type
            if ask_user_hint:
                self.state.last_model_decision.ask_user_hint = ask_user_hint
        self._touch()

    def complete(self, message: str) -> None:
        self.state.task_status = PlannerTaskStatus.COMPLETED
        self.state.final_response = message
        self.state.last_error = None
        self.clear_pending_confirmation()
        self._touch()

    def fail(self, message: str, *, error_code: str = "task_failed", technical_detail: str = "") -> None:
        self.state.task_status = PlannerTaskStatus.FAILED
        self.state.final_response = message
        self.clear_pending_confirmation()
        self.state.last_error = PlannerTaskErrorRecord(
            code=error_code,
            message=message,
            technical_detail=technical_detail,
        )
        self._touch()

    def cancel(self, message: str) -> None:
        self.state.task_status = PlannerTaskStatus.CANCELLED
        self.state.final_response = message
        self.state.last_error = None
        self.clear_pending_confirmation()
        self._touch()

    def prepare_resume(self, user_message: str) -> None:
        self.state.task_status = PlannerTaskStatus.CREATED
        self.state.final_response = ""
        self.state.last_user_message = user_message
        self.state.last_error = None
        self._touch()

    def prepare_retry(self) -> None:
        self.state.task_status = PlannerTaskStatus.CREATED
        self.state.current_iteration = 0
        self.state.memory.clear()
        self.state.pending_steps.clear()
        self.state.completed_steps.clear()
        self.state.selected_skills.clear()
        self.clear_pending_confirmation()
        self.state.execution_events.clear()
        self.state.harness_events.clear()
        self.state.last_model_decision = None
        self.state.last_tool_results.clear()
        self.state.final_response = ""
        self.state.last_error = None
        self._touch()

    def set_pending_confirmation_tool_calls(self, tool_calls: List[ToolCallSpec]) -> None:
        self.state.pending_confirmation_tool_calls = [
            ToolCallSpec(tool_name=item.tool_name, arguments=dict(item.arguments))
            for item in (tool_calls or [])
        ]
        self._touch()

    def clear_pending_confirmation(self) -> None:
        self.state.pending_confirmation_tool_calls.clear()

    def active_step(self) -> str:
        if self.state.pending_steps:
            return self.state.pending_steps[0]
        if self.state.completed_steps:
            return self.state.completed_steps[-1]
        if self.state.final_response:
            return self.state.final_response
        return ""

    def _update_steps(self, decision: PlannerDecision) -> None:
        if decision.suggested_steps:
            normalized_steps = []
            for raw_step in decision.suggested_steps:
                step = (raw_step or "").strip()
                if step and step not in normalized_steps:
                    normalized_steps.append(step)

            completed = [step for step in self.state.completed_steps if step in normalized_steps]
            self.state.completed_steps = completed
            self.state.pending_steps = [step for step in normalized_steps if step not in completed]

        summary = (decision.intent or decision.user_message or decision.next_action.value).strip()

        if decision.next_action == PlannerActionType.CALL_TOOL:
            if not self.state.pending_steps:
                self.state.pending_steps = [
                    f"执行工具: {tool_call.tool_name}"
                    for tool_call in decision.tool_calls
                ]

            if self.state.pending_steps:
                next_step = self.state.pending_steps.pop(0)
                self.state.completed_steps.append(next_step)
            else:
                for tool_call in decision.tool_calls:
                    self.state.completed_steps.append(f"执行工具: {tool_call.tool_name}")

        elif decision.next_action == PlannerActionType.ASK_USER:
            if summary and summary not in self.state.completed_steps and summary not in self.state.pending_steps:
                self.state.pending_steps.append(summary)

        elif decision.next_action in {PlannerActionType.RESPOND, PlannerActionType.FINISH}:
            self.state.pending_steps = [step for step in self.state.pending_steps if step != summary]
            if summary and summary not in self.state.completed_steps:
                self.state.completed_steps.append(summary)

    def _touch(self) -> None:
        self.state.updated_at = utc_now()
