import json
import math
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import HTTPException

from gateway.provider_client import call_provider
from gateway.service import GatewayModelService
from cadmcp.cad_bridge_client import CadLocalBridgeClient
from cadmcp.tool_executor import CadToolExecutor
from planner.decision_parser import PlannerDecisionParserError
from planner.memory_store import InMemoryPlannerStore
from planner.runtime import PlannerRuntime
from planner.session import PlannerObservation, PlannerSession
from planner.task_service import PlannerTaskService
from shared.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    HarnessEventResponse,
    PlannerExecutionEvent,
    PlannerState,
    PlannerTaskEventsResponse,
    PlannerTaskLocalResultRequest,
    PlannerTaskPermissionDecisionRequest,
    PlannerTaskErrorResponse,
    PlannerTaskDetailResponse,
    PlannerTaskResumeRequest,
    PlannerTaskSummaryResponse,
)


PlannerProviderCaller = Callable[[ChatMessageRequest, Optional[str], Optional[str]], Awaitable[str]]


PLANNER_DECISION_SYSTEM_PROMPT = (
    "你是 AgentBridge 智能体模式中的 Planner。\n\n"
    "你的职责不是直接输出 CAD commands，而是输出下一步结构化决策 JSON。\n\n"
    "你必须只输出一个 JSON 对象，不要输出 markdown，不要输出额外解释。\n"
    "JSON 必须包含以下字段：\n"
    "{\n"
    "  \"intent\": \"当前阶段目标\",\n"
    "  \"reasoning_summary\": \"简短推理摘要\",\n"
    "  \"next_action\": \"respond | ask_user | call_tool | finish\",\n"
    "  \"tool_calls\": [{\"tool_name\": \"工具名\", \"arguments\": {}}],\n"
    "  \"selected_skills\": [\"匹配到的 skill_id\"],\n"
    "  \"completion_check\": false,\n"
    "  \"user_message\": \"要返回给用户的阶段性反馈\",\n"
    "  \"ask_user_type\": \"missing_dimension | missing_target | missing_constraint | missing_context | skill_parameters | none\",\n"
    "  \"ask_user_hint\": \"如果需要补充信息，请给出一句明确提示\",\n"
    "  \"suggested_steps\": [\"读取图纸状态\", \"确认关键约束\", \"执行修改\"]\n"
    "}\n\n"
    "可用工具名以 available_tools 为唯一准则；当前产品只提供图纸读取、功能识别、外围轮廓、图层统一及其安全基础工具。\n"
    "输入里会包含 available_tools 和 available_skills 字段，表示当前可用的原子工具目录和技能目录。\n"
    "规则：\n"
    "1. 如果任务涉及当前图纸分析或增量修改，优先先读取图纸状态，再决定绘制动作。\n"
    "2. 如果信息不足以安全绘制，使用 ask_user。\n"
    "3. 只有在确实需要工具时才使用 call_tool。\n"
    "4. 如果任务已经完成，使用 finish。\n"
    "5. ask_user 时必须同时填写 ask_user_type 和 ask_user_hint。\n"
    "6. suggested_steps 要尽量稳定，便于 UI 展示任务步骤。\n"
    "7. 只能从 available_tools 中选择可用 tool_name。\n"
    "8. 优先参考 available_skills 中最匹配的技能，再从该技能关联的 mcp_tools 中选择 tool_calls。\n"
    "9. 如果某个技能明显匹配当前任务，把对应 skill_id 写进 selected_skills；如果没有明显匹配，返回空数组。\n"
    "10. 对没有 auto_tool_calls 的参数化技能，必须在 tool_calls 中补齐可执行工具参数；如果缺少图层名、尺寸、位置或内容，使用 ask_user，并把 ask_user_type 设为 skill_parameters。\n"
    "11. 不要输出 commands 字段，不要直接输出 CAD 绘图 JSON。"
)


def _normalize_agent_approval(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"execute", "run_for_me"}:
        return "execute"
    if normalized in {"full", "full_approval"}:
        return "full"
    return "annotate"


def _build_agent_approval_instruction(value: str) -> str:
    approval = _normalize_agent_approval(value)
    if approval == "execute":
        return (
            "权限策略：替我执行。你可以自动读取上下文、分析并生成低风险预览；"
            "任何真实写入、删除、覆盖、批量修改仍必须通过 confirm_write 等待用户确认。"
        )
    if approval == "full":
        return (
            "权限策略：完全批准。当前会话中可尽量自动执行低风险步骤；"
            "删除、覆盖、批量修改和高风险写图仍必须等待用户确认。"
        )
    return (
        "权限策略：请求批注。关键工具调用和预览生成前应优先请求用户确认或补充批注；"
        "所有真实写入 CAD 的操作必须等待用户确认。"
    )


class PlannerAgentService:
    def __init__(
        self,
        *,
        store: Optional[InMemoryPlannerStore] = None,
        task_service: Optional[PlannerTaskService] = None,
        provider_caller: PlannerProviderCaller = call_provider,
        cad_bridge_client: Optional[CadLocalBridgeClient] = None,
        gateway_service: Optional[GatewayModelService] = None,
        tool_executor: Optional[CadToolExecutor] = None,
    ) -> None:
        self._store = store or InMemoryPlannerStore()
        self._task_service = task_service or PlannerTaskService(store=self._store)
        self._gateway_service = gateway_service or GatewayModelService(provider_caller=provider_caller)
        self._tool_executor = tool_executor or CadToolExecutor(cad_bridge_client=cad_bridge_client)

    async def run_draw_request(self, request: ChatMessageRequest) -> ChatMessageResponse:
        session = self._resolve_session(request)
        self._prepare_session(session, request)

        runtime = PlannerRuntime(
            decision_provider=lambda model_input: self._request_decision(request, model_input),
            tool_executor=self._execute_tool,
        )

        try:
            result = await runtime.run_until_pause_or_completion(session)
        except PlannerDecisionParserError as exc:
            session.fail(
                "Planner 决策解析失败，请稍后重试。",
                error_code="planner_decision_parse_failed",
                technical_detail=str(exc),
            )
            self._task_service.save_task(session)
            raise HTTPException(status_code=502, detail=f"Planner 决策解析失败: {exc}") from exc
        except Exception as exc:
            session.fail(
                "Planner 运行失败，请检查后端或工具链状态后重试。",
                error_code="planner_runtime_failed",
                technical_detail=str(exc),
            )
            self._task_service.save_task(session)
            raise HTTPException(status_code=502, detail=f"Planner 运行失败: {exc}") from exc

        self._task_service.save_task(session)
        planner_state = PlannerState(
            trace_id=session.state.trace_id or None,
            task_status=result.task_status,
            agent_approval=session.state.agent_approval,
            pending_permission_action=self._resolve_pending_permission_action(result.task_status, result.ask_user_type),
            permission_summary=self._build_permission_summary(session.state.agent_approval, result.task_status, result.ask_user_type),
            executed_tools=result.executed_tools,
            selected_skills=result.selected_skills,
            execution_events=[
                PlannerExecutionEvent(
                    tool_name=event.tool_name,
                    status=event.status,
                    summary=event.summary,
                    request_id=event.request_id or None,
                    trace_id=event.trace_id or session.state.trace_id or None,
                    error_code=event.error_code or None,
                    details=event.details or None,
                )
                for event in result.execution_events
            ],
            completed_steps=result.completed_steps,
            pending_steps=result.pending_steps,
            ask_user_type=result.ask_user_type or None,
            ask_user_hint=result.ask_user_hint or None,
        )
        return ChatMessageResponse(
            reply_text=self._build_reply_text(result),
            commands=[],
            legacy_fallback_used=False,
            planner_session_id=session.state.session_id,
            trace_id=session.state.trace_id or None,
            planner_state=planner_state,
            task_status=planner_state.task_status,
            executed_tools=list(planner_state.executed_tools),
            selected_skills=list(planner_state.selected_skills),
            execution_events=list(planner_state.execution_events),
            planner_completed_steps=list(planner_state.completed_steps),
            planner_pending_steps=list(planner_state.pending_steps),
            ask_user_type=planner_state.ask_user_type,
            ask_user_hint=planner_state.ask_user_hint,
        )

    def list_recent_tasks(self, limit: int = 10, status_filter: Optional[str] = None) -> list[PlannerTaskSummaryResponse]:
        summaries = self._task_service.list_recent_tasks(limit=limit, status_filter=status_filter)
        return [
            PlannerTaskSummaryResponse(
                task_id=summary.task_id,
                trace_id=summary.trace_id or None,
                user_goal=summary.user_goal,
                task_status=summary.task_status,
                last_user_message=summary.last_user_message,
                active_step=summary.active_step,
                created_at=summary.created_at,
                updated_at=summary.updated_at,
                resumable=summary.resumable,
                retryable=summary.retryable,
                cancellable=summary.cancellable,
                last_error=(
                    PlannerTaskErrorResponse(
                        code=summary.last_error.code,
                        message=summary.last_error.message,
                        technical_detail=summary.last_error.technical_detail or None,
                    )
                    if summary.last_error is not None
                    else None
                ),
            )
            for summary in summaries
        ]

    def get_task(self, task_id: str) -> Optional[PlannerTaskDetailResponse]:
        session = self._task_service.get_task(task_id)
        if session is None:
            return None
        return self._build_task_detail_response(session)

    def get_task_events(self, task_id: str) -> Optional[PlannerTaskEventsResponse]:
        session = self._task_service.get_task(task_id)
        if session is None:
            return None
        return PlannerTaskEventsResponse(
            task_id=task_id,
            events=[
                HarnessEventResponse(
                    event_id=event.event_id,
                    session_id=event.session_id,
                    task_id=event.task_id,
                    event_type=event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                    sequence=event.sequence,
                    timestamp=event.timestamp,
                    summary=event.summary,
                    step_id=event.step_id,
                    payload=dict(event.payload or {}),
                    visible_to_user=event.visible_to_user,
                    collapse_default=event.collapse_default,
                    trace_id=event.trace_id or None,
                )
                for event in session.state.harness_events
            ],
        )

    def cancel_task(self, task_id: str) -> Optional[PlannerTaskDetailResponse]:
        session = self._task_service.cancel_task(task_id)
        if session is None:
            return None
        return self._build_task_detail_response(session)

    def record_local_result(self, task_id: str, request: PlannerTaskLocalResultRequest) -> Optional[PlannerTaskDetailResponse]:
        session = self._task_service.record_local_result(
            task_id,
            status=request.status,
            message=request.message,
            affected_entities_count=request.affected_entities_count,
            trace_id=request.trace_id or "",
            tool_name=request.tool_name,
            details=request.details,
        )
        if session is None:
            return None
        return self._build_task_detail_response(session)

    def record_permission_decision(self, task_id: str, request: PlannerTaskPermissionDecisionRequest) -> Optional[PlannerTaskDetailResponse]:
        session = self._task_service.record_permission_decision(
            task_id,
            decision=request.decision,
            message=request.message,
            trace_id=request.trace_id or "",
            details=request.details,
        )
        if session is None:
            return None
        return self._build_task_detail_response(session)

    async def resume_task(self, task_id: str, request: PlannerTaskResumeRequest) -> Optional[ChatMessageResponse]:
        message = (request.message or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")

        session = self._task_service.resume_task(task_id, message)
        if session is None:
            return None

        return await self.run_draw_request(
            ChatMessageRequest(
                message=message,
                mode="draw",
                planner_session_id=task_id,
                trace_id=session.state.trace_id,
            )
        )

    async def retry_task(self, task_id: str) -> Optional[ChatMessageResponse]:
        session = self._task_service.retry_task(task_id)
        if session is None:
            return None

        message = (session.state.last_user_message or session.state.user_goal or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="task has no retryable message")

        return await self.run_draw_request(
            ChatMessageRequest(
                message=message,
                mode="draw",
                planner_session_id=task_id,
                trace_id=session.state.trace_id,
            )
        )

    def _resolve_session(self, request: ChatMessageRequest) -> PlannerSession:
        trace_id = (request.trace_id or "").strip() or str(uuid.uuid4())
        return self._task_service.resolve_session(
            request.planner_session_id,
            request.message.strip(),
            trace_id=trace_id,
        )

    @staticmethod
    def _prepare_session(session: PlannerSession, request: ChatMessageRequest) -> None:
        message = (request.message or "").strip()
        trace_id = (request.trace_id or "").strip()
        approval = _normalize_agent_approval(request.agent_approval)
        session.state.agent_approval = approval
        if trace_id:
            session.state.trace_id = trace_id
        elif not session.state.trace_id:
            session.state.trace_id = str(uuid.uuid4())
        if message:
            session.state.last_user_message = message
            session.record_observation(
                PlannerObservation(
                    source="user",
                    payload={"message": message, "trace_id": session.state.trace_id, "agent_approval": approval},
                    is_error=False,
                )
            )

    async def _request_decision(self, request: ChatMessageRequest, model_input: Dict[str, Any]) -> str:
        deterministic_decision = self._build_deterministic_decision(request.message)
        if deterministic_decision is not None:
            return json.dumps(deterministic_decision, ensure_ascii=False)

        planner_request = ChatMessageRequest(
            message=request.message,
            image_base64=request.image_base64,
            mode="planner",
            model=request.model,
            provider=request.provider,
            api_key=request.api_key,
            api_base_url=request.api_base_url,
            planner_session_id=request.planner_session_id,
            trace_id=request.trace_id,
            agent_approval=request.agent_approval,
        )
        prompt = self._build_decision_prompt(model_input, request.agent_approval)
        return await self._gateway_service.request_text(planner_request, PLANNER_DECISION_SYSTEM_PROMPT, prompt)

    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        return await self._tool_executor.execute_tool(tool_name, arguments, caller="planner_runtime", dry_run=dry_run)

    @staticmethod
    def _build_decision_prompt(model_input: Dict[str, Any], agent_approval: Optional[str] = None) -> str:
        approval = _normalize_agent_approval(agent_approval)
        approval_instruction = _build_agent_approval_instruction(approval)
        return (
            "请基于下面的 Planner 会话状态，输出下一步结构化决策 JSON。\n\n"
            f"AgentApproval: {approval}\n"
            f"{approval_instruction}\n\n"
            "PlannerState:\n"
            f"{json.dumps(model_input, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _build_deterministic_decision(message: str) -> Optional[Dict[str, Any]]:
        text = (message or "").strip()
        if not text:
            return None

        explicit_geometry = PlannerAgentService._build_circle_rectangle_area_decision(text)
        if explicit_geometry is not None:
            return explicit_geometry

        normalized = text.replace(" ", "")
        required_fragments = ("原点", "圆", "矩形", "正方形", "面积")
        if not all(fragment in normalized for fragment in required_fragments):
            return None

        radius_match = re.search(r"半径\s*([0-9]+(?:\.[0-9]+)?)", text)
        if radius_match is None:
            return None

        radius = float(radius_match.group(1))
        if radius <= 0:
            return None

        rectangle_half_extent = radius / math.sqrt(2.0)
        inner_circle_radius = rectangle_half_extent
        square_half_extent = inner_circle_radius / math.sqrt(2.0)
        square_side = square_half_extent * 2.0
        square_area = square_side * square_side

        def round_value(value: float) -> float:
            return round(value, 4)

        commands = [
            {
                "type": "CIRCLE",
                "center": [0, 0],
                "radius": round_value(radius),
                "layer": "AI_GEOMETRY",
                "color": 1,
            },
            {
                "type": "RECTANGLE",
                "start": [-round_value(rectangle_half_extent), -round_value(rectangle_half_extent)],
                "end": [round_value(rectangle_half_extent), round_value(rectangle_half_extent)],
                "layer": "AI_GEOMETRY",
                "color": 2,
            },
            {
                "type": "CIRCLE",
                "center": [0, 0],
                "radius": round_value(inner_circle_radius),
                "layer": "AI_GEOMETRY",
                "color": 3,
            },
            {
                "type": "POLYLINE",
                "points": [
                    [-round_value(square_half_extent), -round_value(square_half_extent)],
                    [round_value(square_half_extent), -round_value(square_half_extent)],
                    [round_value(square_half_extent), round_value(square_half_extent)],
                    [-round_value(square_half_extent), round_value(square_half_extent)],
                ],
                "closed": True,
                "layer": "AI_GEOMETRY",
                "color": 4,
            },
            {
                "type": "TEXT",
                "content": f"正方形面积: {round_value(square_area)}",
                "position": [round_value(radius + radius * 0.15), 0],
                "height": max(round_value(radius * 0.08), 1.0),
                "layer": "TEXT",
                "color": 7,
            },
        ]

        return {
            "intent": "绘制嵌套几何图形并标注面积",
            "reasoning_summary": "识别为确定性嵌套几何绘制任务，使用 execute_draw_batch 生成写入前预览。",
            "next_action": "call_tool",
            "tool_calls": [
                {
                    "tool_name": "execute_draw_batch",
                    "arguments": {"commands": commands},
                }
            ],
            "selected_skills": [],
            "completion_check": True,
            "user_message": "已计算嵌套几何尺寸，准备生成更改预览。",
            "ask_user_type": "none",
            "ask_user_hint": "",
            "suggested_steps": [
                "计算嵌套几何尺寸",
                "预演批量绘图命令",
                "等待确认后写入图纸",
            ],
        }

    @staticmethod
    def _build_circle_rectangle_area_decision(text: str) -> Optional[Dict[str, Any]]:
        normalized = re.sub(r"\s+", "", text or "")
        required_fragments = ("原点", "半径", "圆", "长方形", "面积")
        if not all(fragment in normalized for fragment in required_fragments):
            return None

        radius_match = re.search(r"半径\s*([0-9]+(?:\.[0-9]+)?)\s*(?:米|m|M)?", text)
        if radius_match is None:
            return None

        radius = float(radius_match.group(1))
        if radius <= 0:
            return None

        half_extent = radius / math.sqrt(2.0)
        side = half_extent * 2.0
        area = side * side

        def round_value(value: float) -> float:
            return round(value, 4)

        commands = [
            {
                "type": "CIRCLE",
                "center": [0, 0],
                "radius": round_value(radius),
                "layer": "AI_GEOMETRY",
                "color": 1,
            },
            {
                "type": "RECTANGLE",
                "start": [-round_value(half_extent), -round_value(half_extent)],
                "end": [round_value(half_extent), round_value(half_extent)],
                "layer": "AI_GEOMETRY",
                "color": 2,
            },
            {
                "type": "TEXT",
                "content": f"矩形面积: {round_value(area)} m2",
                "position": [round_value(radius * 1.15), 0],
                "height": max(round_value(radius * 0.08), 1.0),
                "layer": "TEXT",
                "color": 7,
            },
        ]

        return {
            "intent": "绘制原点圆、圆内最大内接矩形并标注面积",
            "reasoning_summary": "识别为确定性几何绘图任务；长方形未指定长宽时，采用圆内最大内接矩形（正方形）作为默认方案。",
            "next_action": "call_tool",
            "tool_calls": [
                {
                    "tool_name": "execute_draw_batch",
                    "arguments": {"commands": commands},
                }
            ],
            "selected_skills": [],
            "completion_check": True,
            "user_message": "已计算圆内最大内接矩形尺寸，并生成更改预览；确认后会应用到当前图纸。",
            "ask_user_type": "none",
            "ask_user_hint": "",
            "suggested_steps": [
                "绘制半径圆",
                "计算并绘制圆内最大内接矩形",
                "标注矩形面积",
                "等待本地确认写入",
            ],
        }

    @staticmethod
    def _build_reply_text(result: Any) -> str:
        if result.final_response:
            return result.final_response

        if result.executed_tools:
            return "任务已执行，已调用工具: " + ", ".join(result.executed_tools)

        return "智能体任务已处理完成。"

    def _build_task_detail_response(self, session: PlannerSession) -> PlannerTaskDetailResponse:
        ask_user_type = session.state.last_model_decision.ask_user_type if session.state.last_model_decision else ""
        planner_state = PlannerState(
            trace_id=session.state.trace_id or None,
            task_status=session.state.task_status.value,
            agent_approval=session.state.agent_approval,
            pending_permission_action=self._resolve_pending_permission_action(session.state.task_status.value, ask_user_type),
            permission_summary=self._build_permission_summary(session.state.agent_approval, session.state.task_status.value, ask_user_type),
            executed_tools=[event.tool_name for event in session.state.execution_events],
            selected_skills=list(session.state.selected_skills),
            execution_events=[
                PlannerExecutionEvent(
                    tool_name=event.tool_name,
                    status=event.status,
                    summary=event.summary,
                    request_id=event.request_id or None,
                    trace_id=event.trace_id or session.state.trace_id or None,
                    error_code=event.error_code or None,
                    details=event.details or None,
                )
                for event in session.state.execution_events
            ],
            completed_steps=list(session.state.completed_steps),
            pending_steps=list(session.state.pending_steps),
            ask_user_type=ask_user_type or None,
            ask_user_hint=(session.state.last_model_decision.ask_user_hint if session.state.last_model_decision else None),
        )
        return PlannerTaskDetailResponse(
            task_id=session.state.session_id,
            trace_id=session.state.trace_id or None,
            user_goal=session.state.user_goal,
            task_status=session.state.task_status.value,
            last_user_message=session.state.last_user_message,
            active_step=session.active_step(),
            created_at=session.state.created_at,
            updated_at=session.state.updated_at,
            resumable=self._task_service.is_resumable(session),
            retryable=self._task_service.is_retryable(session),
            cancellable=self._task_service.is_cancellable(session),
            final_response=session.state.final_response,
            planner_state=planner_state,
            last_error=(
                PlannerTaskErrorResponse(
                    code=session.state.last_error.code,
                    message=session.state.last_error.message,
                    technical_detail=session.state.last_error.technical_detail or None,
                )
                if session.state.last_error is not None
                else None
            ),
        )

    @staticmethod
    def _resolve_pending_permission_action(task_status: str, ask_user_type: str) -> Optional[str]:
        if str(task_status or "").strip().lower() != "waiting_user":
            return None
        normalized_ask = str(ask_user_type or "").strip().lower()
        if normalized_ask == "confirm_write":
            return "confirm_write"
        if normalized_ask:
            return normalized_ask
        return None

    @staticmethod
    def _build_permission_summary(agent_approval: str, task_status: str, ask_user_type: str) -> Optional[str]:
        pending_action = PlannerAgentService._resolve_pending_permission_action(task_status, ask_user_type)
        approval = _normalize_agent_approval(agent_approval)
        if pending_action == "confirm_write":
            return f"{approval}: waiting for local drawing write approval"
        if pending_action:
            return f"{approval}: waiting for user input"
        if str(task_status or "").strip().lower() in {"completed", "failed", "cancelled"}:
            return f"{approval}: task is terminal"
        return f"{approval}: policy active"
