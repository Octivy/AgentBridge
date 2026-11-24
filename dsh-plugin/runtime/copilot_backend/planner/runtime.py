import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from harness.events import HarnessEventType, make_harness_event
from harness.permissions import PermissionBehavior, evaluate_permission, normalize_approval_policy
from cadmcp.tool_registry import get_product_tool as get_tool
from planner.decision_parser import PlannerDecisionParser
from planner.prompt_builder import PlannerPromptBuilder
from planner.session import (
    PlannerActionType,
    PlannerExecutionEventRecord,
    PlannerObservation,
    PlannerSession,
    PlannerTaskStatus,
    ToolCallSpec,
)
from skills.registry import expand_skills_to_tool_calls, get_enabled_skill as get_skill


ModelDecisionProvider = Callable[[Dict[str, Any]], Awaitable[Any]]
ToolExecutor = Callable[[str, Dict[str, Any], bool], Awaitable[Dict[str, Any]]]


@dataclass
class PlannerExecutionEventResult:
    tool_name: str
    status: str
    summary: str = ""
    request_id: str = ""
    trace_id: str = ""
    error_code: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerRuntimeResult:
    session_id: str
    task_status: str
    iterations: int
    user_messages: List[str] = field(default_factory=list)
    executed_tools: List[str] = field(default_factory=list)
    selected_skills: List[str] = field(default_factory=list)
    execution_events: List[PlannerExecutionEventResult] = field(default_factory=list)
    final_response: str = ""
    completed_steps: List[str] = field(default_factory=list)
    pending_steps: List[str] = field(default_factory=list)
    ask_user_type: str = ""
    ask_user_hint: str = ""


class PlannerRuntime:
    """Planner runtime with a conservative dry_run-first policy for write tools."""

    def __init__(
        self,
        *,
        decision_provider: ModelDecisionProvider,
        tool_executor: ToolExecutor,
        prompt_builder: Optional[PlannerPromptBuilder] = None,
        decision_parser: Optional[PlannerDecisionParser] = None,
    ) -> None:
        self._decision_provider = decision_provider
        self._tool_executor = tool_executor
        self._prompt_builder = prompt_builder or PlannerPromptBuilder()
        self._decision_parser = decision_parser or PlannerDecisionParser()

    async def run_until_pause_or_completion(self, session: PlannerSession) -> PlannerRuntimeResult:
        session.mark_running()
        user_messages: List[str] = []
        executed_tools: List[str] = []
        execution_events: List[PlannerExecutionEventResult] = []

        if await self._try_execute_pending_confirmation(session, executed_tools, execution_events):
            return self._build_runtime_result(session, user_messages, executed_tools, execution_events)

        while self._should_continue(session) and not self._hit_iteration_limit(session):
            model_input = self._prompt_builder.build(session.state)
            raw_decision = await self._decision_provider(model_input)
            decision = self._decision_parser.parse(raw_decision)
            session.apply_decision(decision)
            if decision.suggested_steps:
                self._emit_event(
                    session,
                    HarnessEventType.PLAN_CREATED,
                    "Planner created or revised task plan.",
                    {
                        "pending_steps": list(session.state.pending_steps),
                        "completed_steps": list(session.state.completed_steps),
                        "suggested_steps": list(decision.suggested_steps),
                    },
                )

            if decision.user_message:
                user_messages.append(decision.user_message)

            if decision.next_action == PlannerActionType.RESPOND:
                session.complete(decision.user_message or "Planner responded successfully.")
                break

            if decision.next_action == PlannerActionType.ASK_USER:
                session.wait_for_user(decision.user_message or "More information is required.")
                break

            if decision.next_action == PlannerActionType.FINISH:
                session.complete(decision.user_message or "Planner task completed.")
                break

            if decision.next_action == PlannerActionType.CALL_TOOL:
                tool_calls = self._resolve_tool_calls(decision)
                if not tool_calls:
                    clarification_message = self._build_missing_skill_parameters_message(decision.selected_skills)
                    session.wait_for_user_with_hint(
                        clarification_message,
                        ask_user_type="skill_parameters",
                        ask_user_hint=clarification_message,
                    )
                    break

                session.clear_pending_confirmation()
                previewed_calls: List[ToolCallSpec] = []
                previewed_events: List[PlannerExecutionEventResult] = []
                preview_failed = False

                for tool_call in tool_calls:
                    preview_only = self._should_preview_before_write(session, tool_call)
                    self._emit_event(
                        session,
                        HarnessEventType.TOOL_REQUESTED,
                        tool_call.tool_name,
                        {"arguments": dict(tool_call.arguments), "dry_run": preview_only},
                    )
                    result = await self._execute_tool_call(
                        session,
                        tool_call,
                        executed_tools,
                        execution_events,
                        dry_run=preview_only,
                    )
                    if not bool(result.get("ok", True)):
                        preview_failed = True
                        session.fail(
                            result.get("error_message") or "Tool execution failed.",
                            error_code=result.get("error_code") or "tool_execution_failed",
                            technical_detail=result.get("summary") or "",
                        )
                        break

                    if preview_only:
                        authorized_call = self._bind_preview_authorization(tool_call, result)
                        if self._is_policy_auto_approved(session, tool_call):
                            self._emit_event(
                                session,
                                HarnessEventType.PERMISSION_DECISION,
                                "Write approved by task policy after dry-run preview.",
                                {"tool_name": tool_call.tool_name, "decision": "allow", "source": "agent_approval"},
                            )
                            commit_result = await self._execute_tool_call(
                                session,
                                authorized_call,
                                executed_tools,
                                execution_events,
                                dry_run=False,
                            )
                            if not bool(commit_result.get("ok", True)):
                                preview_failed = True
                                session.fail(
                                    commit_result.get("error_message") or "Tool execution failed.",
                                    error_code=commit_result.get("error_code") or "tool_execution_failed",
                                    technical_detail=commit_result.get("summary") or "",
                                )
                                break
                        else:
                            previewed_calls.append(authorized_call)
                            previewed_events.append(execution_events[-1])

                if preview_failed:
                    break

                if previewed_calls and not preview_failed:
                    session.set_pending_confirmation_tool_calls(previewed_calls)
                    confirmation_message = self._build_confirmation_request_message(previewed_events)
                    self._emit_event(
                        session,
                        HarnessEventType.PERMISSION_REQUESTED,
                        confirmation_message,
                        {
                            "ask_user_type": "confirm_write",
                            "tool_calls": [item.tool_name for item in previewed_calls],
                        },
                    )
                    session.wait_for_user_with_hint(
                        confirmation_message,
                        ask_user_type="confirm_write",
                        ask_user_hint=confirmation_message,
                    )
                    break

                if decision.completion_check:
                    session.complete(decision.user_message or "Planner task completed.")
                    break

        if self._hit_iteration_limit(session):
            session.fail("Planner reached the maximum iteration count and stopped.", error_code="iteration_limit_reached")

        return self._build_runtime_result(session, user_messages, executed_tools, execution_events)

    @staticmethod
    def _emit_event(
        session: PlannerSession,
        event_type: HarnessEventType,
        summary: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.append_harness_event(
            make_harness_event(
                session_id=session.state.session_id,
                task_id=session.state.session_id,
                event_type=event_type,
                sequence=session.next_harness_event_sequence(),
                summary=summary,
                payload=payload or {},
                trace_id=session.state.trace_id,
            )
        )

    def _build_runtime_result(
        self,
        session: PlannerSession,
        user_messages: List[str],
        executed_tools: List[str],
        execution_events: List[PlannerExecutionEventResult],
    ) -> PlannerRuntimeResult:
        return PlannerRuntimeResult(
            session_id=session.state.session_id,
            task_status=session.state.task_status.value,
            iterations=session.state.current_iteration,
            user_messages=user_messages,
            executed_tools=executed_tools,
            selected_skills=list(session.state.selected_skills),
            execution_events=execution_events,
            final_response=session.state.final_response,
            completed_steps=list(session.state.completed_steps),
            pending_steps=list(session.state.pending_steps),
            ask_user_type=session.state.last_model_decision.ask_user_type if session.state.last_model_decision else "",
            ask_user_hint=session.state.last_model_decision.ask_user_hint if session.state.last_model_decision else "",
        )

    @staticmethod
    def _resolve_tool_calls(decision: Any) -> List[ToolCallSpec]:
        expanded_calls = [
            ToolCallSpec(
                tool_name=item.tool_name,
                arguments=dict(item.arguments),
            )
            for item in expand_skills_to_tool_calls(decision.selected_skills)
        ]
        explicit_calls = list(decision.tool_calls)

        merged_calls: List[ToolCallSpec] = []
        seen = set()
        for tool_call in expanded_calls + explicit_calls:
            key = PlannerRuntime._tool_call_key(tool_call)
            if key in seen:
                continue
            seen.add(key)
            merged_calls.append(tool_call)
        return merged_calls

    @staticmethod
    def _tool_call_key(tool_call: ToolCallSpec) -> str:
        return json.dumps(
            {"tool_name": tool_call.tool_name, "arguments": tool_call.arguments},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _bind_preview_authorization(tool_call: ToolCallSpec, result: Dict[str, Any]) -> ToolCallSpec:
        arguments = dict(tool_call.arguments or {})
        for key in ("permission_token", "preview_hash", "permission_request_id"):
            value = result.get(key)
            if value not in (None, ""):
                arguments[key] = value
        return ToolCallSpec(tool_name=tool_call.tool_name, arguments=arguments)

    async def _try_execute_pending_confirmation(
        self,
        session: PlannerSession,
        executed_tools: List[str],
        execution_events: List[PlannerExecutionEventResult],
    ) -> bool:
        pending_calls = list(session.state.pending_confirmation_tool_calls)
        if not pending_calls:
            return False

        if not self._is_confirmation_message(session.state.last_user_message):
            session.clear_pending_confirmation()
            return False

        session.clear_pending_confirmation()
        for tool_call in pending_calls:
            result = await self._execute_tool_call(
                session,
                tool_call,
                executed_tools,
                execution_events,
                dry_run=False,
                confirmed_by_local_user=True,
            )
            if not bool(result.get("ok", True)):
                session.fail(
                    result.get("error_message") or "Tool execution failed.",
                    error_code=result.get("error_code") or "tool_execution_failed",
                    technical_detail=result.get("summary") or "",
                )
                return True

        session.complete(self._build_confirmation_completion_message(execution_events))
        return True

    async def _execute_tool_call(
        self,
        session: PlannerSession,
        tool_call: ToolCallSpec,
        executed_tools: List[str],
        execution_events: List[PlannerExecutionEventResult],
        *,
        dry_run: bool,
        confirmed_by_local_user: bool = False,
    ) -> Dict[str, Any]:
        tool_arguments = dict(tool_call.arguments or {})
        trace_id = (session.state.trace_id or "").strip()
        if trace_id:
            tool_arguments.setdefault("trace_id", trace_id)
        if not dry_run:
            tool_arguments.setdefault("task_id", session.state.session_id)
        if confirmed_by_local_user:
            tool_arguments.setdefault("confirmed_by_local_user", True)
        event_arguments = self._redact_sensitive_mapping(tool_arguments)

        self._emit_event(
            session,
            HarnessEventType.TOOL_STARTED,
            tool_call.tool_name,
            {"arguments": event_arguments, "dry_run": dry_run},
        )
        result = await self._tool_executor(tool_call.tool_name, tool_arguments, dry_run)
        event_result = self._redact_sensitive_mapping(result)
        executed_tools.append(tool_call.tool_name)
        event = self._build_execution_event(
            tool_call.tool_name,
            result,
            trace_id=trace_id,
            task_id=session.state.session_id,
            dry_run=dry_run,
            confirmed_by_local_user=confirmed_by_local_user,
            agent_approval=session.state.agent_approval,
        )
        execution_events.append(event)
        self._emit_event(
            session,
            HarnessEventType.TOOL_RESULT,
            event.summary,
            {
                "tool_name": tool_call.tool_name,
                "status": event.status,
                "dry_run": dry_run,
                "result": event_result,
                "event": {
                    "request_id": event.request_id,
                    "trace_id": event.trace_id,
                    "error_code": event.error_code,
                    "details": dict(event.details),
                },
            },
        )
        if dry_run and bool(result.get("ok", True)):
            self._emit_event(
                session,
                HarnessEventType.DRY_RUN_PREVIEW_CREATED,
                event.summary,
                {"tool_name": tool_call.tool_name, "result": event_result},
            )
        session.state.execution_events.append(
            PlannerExecutionEventRecord(
                tool_name=event.tool_name,
                status=event.status,
                summary=event.summary,
                request_id=event.request_id,
                trace_id=event.trace_id,
                error_code=event.error_code,
                details=dict(event.details),
            )
        )
        session.record_observation(
            PlannerObservation(
                source="tool",
                payload={
                    "tool_name": tool_call.tool_name,
                    "arguments": event_arguments,
                    "result": event_result,
                },
                is_error=not bool(result.get("ok", True)),
            )
        )
        return result

    @staticmethod
    def _redact_sensitive_mapping(value: Dict[str, Any]) -> Dict[str, Any]:
        redacted = dict(value or {})
        if redacted.get("permission_token"):
            redacted["permission_token"] = "***"
        return redacted

    @staticmethod
    def _build_execution_event(
        tool_name: str,
        result: Dict[str, Any],
        *,
        trace_id: str = "",
        task_id: str = "",
        dry_run: bool = False,
        confirmed_by_local_user: bool = False,
        agent_approval: str = "annotate",
    ) -> PlannerExecutionEventResult:
        is_success = bool(result.get("ok", True))
        summary = str(
            result.get("summary")
            or result.get("error_message")
            or ("Tool executed successfully." if is_success else "Tool execution failed.")
        ).strip()
        details = PlannerRuntime._build_execution_event_details(result)
        semantic_summary = PlannerRuntime._build_semantic_result_summary(
            tool_name,
            summary,
            details.get("data") if isinstance(details.get("data"), dict) else {},
        )
        if semantic_summary:
            details["semantic_summary"] = semantic_summary
        normalized_trace_id = str(result.get("trace_id") or trace_id or "").strip()
        if normalized_trace_id:
            details.setdefault("trace_id", normalized_trace_id)
        PlannerRuntime._attach_audit_details(
            details,
            tool_name=tool_name,
            task_id=task_id,
            trace_id=normalized_trace_id,
            request_id=str(result.get("request_id") or "").strip(),
            dry_run=dry_run,
            confirmed_by_local_user=confirmed_by_local_user,
            agent_approval=agent_approval,
        )
        return PlannerExecutionEventResult(
            tool_name=tool_name,
            status="succeeded" if is_success else "failed",
            summary=summary,
            request_id=str(result.get("request_id") or "").strip(),
            trace_id=normalized_trace_id,
            error_code=str(result.get("error_code") or "").strip(),
            details=details,
        )

    @staticmethod
    def _build_execution_event_details(result: Dict[str, Any]) -> Dict[str, Any]:
        details: Dict[str, Any] = {}

        dry_run = result.get("dry_run")
        if isinstance(dry_run, bool):
            details["dry_run"] = dry_run

        affected_entities_count = result.get("affected_entities_count")
        if isinstance(affected_entities_count, int):
            details["affected_entities_count"] = affected_entities_count

        data = result.get("data")
        if isinstance(data, dict) and data:
            details["data"] = data

        return details

    @staticmethod
    def _attach_audit_details(
        details: Dict[str, Any],
        *,
        tool_name: str,
        task_id: str,
        trace_id: str,
        request_id: str,
        dry_run: bool,
        confirmed_by_local_user: bool,
        agent_approval: str,
    ) -> None:
        tool = get_tool(tool_name)
        side_effect_level = str(tool.side_effect_level if tool is not None else "").strip().lower()
        dry_run_supported = bool(tool.dry_run_supported) if tool is not None else False
        approval = str(agent_approval or "annotate").strip().lower()
        policy_approved = approval in {"execute", "full", "full_approval", "run_for_me"} and not dry_run
        confirmation_required = dry_run_supported and side_effect_level not in {"", "none"} and not policy_approved

        audit = {
            "task_id": task_id,
            "trace_id": trace_id,
            "request_id": request_id,
            "tool_name": tool_name,
            "side_effect_level": side_effect_level or "unknown",
            "dry_run": dry_run,
            "confirmation_required": confirmation_required,
            "confirmed_by_local_user": confirmed_by_local_user,
            "agent_approval": approval,
            "approved_by_policy": policy_approved,
            "write_actor": "local_autocad_plugin" if confirmation_required else "planner_runtime",
        }
        if confirmed_by_local_user:
            audit["confirmation_source"] = "local_user_message"

        details["audit"] = audit

    @staticmethod
    def _should_preview_before_write(session: PlannerSession, tool_call: ToolCallSpec) -> bool:
        tool = get_tool(tool_call.tool_name)
        if tool is None or not bool(tool.dry_run_supported):
            return False
        return getattr(tool, "risk_level", "critical") not in {"read_only", "preview_only"}

    @staticmethod
    def _is_policy_auto_approved(session: PlannerSession, tool_call: ToolCallSpec) -> bool:
        tool = get_tool(tool_call.tool_name)
        if tool is None:
            return False
        approval = normalize_approval_policy(getattr(session.state, "agent_approval", "ask"))
        decision = evaluate_permission(approval, getattr(tool, "risk_level", "critical"), dry_run=False)
        return decision.behavior == PermissionBehavior.ALLOW

    @staticmethod
    def _is_confirmation_message(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False

        negative_tokens = ("don't", "do not", "cancel", "stop", "不要", "取消", "停止", "别")
        if any(token in text for token in negative_tokens):
            return False

        positive_tokens = (
            "confirm",
            "confirmed",
            "yes",
            "ok",
            "okay",
            "go ahead",
            "proceed",
            "run it",
            "execute",
            "apply",
            "继续",
            "确认",
            "执行",
            "可以",
            "开始",
            "提交",
            "应用",
        )
        return any(token in text for token in positive_tokens)

    @staticmethod
    def _build_confirmation_request_message(execution_events: List[PlannerExecutionEventResult]) -> str:
        successful = [event for event in execution_events if event is not None and event.status == "succeeded"]
        if not successful:
            return "已生成更改预览。点击“应用到图纸”或回复“确认执行”后，我会把更改应用到当前图纸。"

        fragments = []
        for event in successful:
            summary = PlannerRuntime._build_confirmation_event_summary(event)
            fragments.append(summary if summary else event.tool_name)

        return "已生成更改预览：" + "；".join(fragments) + "。点击“应用到图纸”或回复“确认执行”后，我会把更改应用到当前图纸。"

    @staticmethod
    def _build_confirmation_event_summary(event: PlannerExecutionEventResult) -> str:
        details = event.details if isinstance(event.details, dict) else {}
        data = details.get("data") if isinstance(details.get("data"), dict) else {}

        semantic_summary = str(details.get("semantic_summary") or "").strip()
        if semantic_summary:
            return semantic_summary

        command_count = data.get("command_count")
        if isinstance(command_count, int) and command_count > 0:
            return f"将应用 {command_count} 条绘图命令"

        affected_entities_count = details.get("affected_entities_count")
        if isinstance(affected_entities_count, int) and affected_entities_count > 0:
            return f"预计影响 {affected_entities_count} 个图元"

        layer = str(data.get("layer") or "").strip()
        if layer:
            return f"将确认图层 {layer}"

        summary = (event.summary or "").strip()
        if PlannerRuntime._is_technical_preview_summary(summary):
            return event.tool_name

        return summary

    @staticmethod
    def _build_semantic_result_summary(tool_name: str, summary: str, data: Dict[str, Any]) -> str:
        value = (summary or "").strip()
        if not value or PlannerRuntime._is_technical_preview_summary(value):
            return ""

        if PlannerRuntime._is_architecture_result(tool_name, data):
            return value

        return ""

    @staticmethod
    def _is_architecture_result(tool_name: str, data: Dict[str, Any]) -> bool:
        normalized_tool_name = (tool_name or "").strip().lower()
        if normalized_tool_name.startswith("arch_"):
            return True

        if not isinstance(data, dict):
            return False

        if str(data.get("object_type") or "").strip():
            return True

        if isinstance(data.get("created_object_ids"), list):
            return True

        preview = data.get("preview")
        if isinstance(preview, dict) and str(preview.get("object_type") or "").strip():
            return True

        smart_object = data.get("smart_object")
        return isinstance(smart_object, dict) and str(smart_object.get("object_type") or "").strip() != ""

    @staticmethod
    def _is_technical_preview_summary(summary: str) -> bool:
        value = (summary or "").strip()
        if not value:
            return False

        lower = value.lower()
        return (
            "dry_run" in lower
            or "dry run" in lower
            or "real write" in lower
            or "local autocad" in lower
            or "nas" in lower
            or "已生成更改预览" in value
            or "等待确认后应用到图纸" in value
        )

    @staticmethod
    def _build_confirmation_completion_message(execution_events: List[PlannerExecutionEventResult]) -> str:
        successful = [event for event in execution_events if event is not None and event.status == "succeeded"]
        if not successful:
            return "Confirmed write completed."

        fragments = []
        for event in successful:
            summary = (event.summary or "").strip()
            fragments.append(summary if summary else event.tool_name)

        return "Confirmed write completed: " + "; ".join(fragments) + "."

    @staticmethod
    def _build_missing_skill_parameters_message(skill_ids: List[str]) -> str:
        selected_skills = [get_skill(skill_id) for skill_id in (skill_ids or [])]
        selected_skills = [skill for skill in selected_skills if skill is not None]

        if selected_skills:
            names = "、".join(skill.name for skill in selected_skills)
            return f"已选择 {names} 技能，但还缺少可执行工具参数。请补充目标对象、尺寸、位置或样式信息。"

        return "还缺少可执行工具参数。请补充目标对象、尺寸、位置或样式信息。"

    @staticmethod
    def _should_continue(session: PlannerSession) -> bool:
        return session.state.task_status in {PlannerTaskStatus.RUNNING, PlannerTaskStatus.CREATED}

    @staticmethod
    def _hit_iteration_limit(session: PlannerSession) -> bool:
        return (
            session.state.task_status in {PlannerTaskStatus.RUNNING, PlannerTaskStatus.CREATED}
            and session.state.current_iteration >= session.state.max_iterations
        )
