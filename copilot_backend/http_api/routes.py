"""HTTP surface for the CAD/MCP MVP."""

import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse

from cadmcp.tool_registry import get_product_tool, list_product_tools
from connector_runtime.diagnostics import build_connector_capabilities, build_connector_diagnostics
from http_api.agent_handler import handle_agent_draw
from http_api.chat_handler import handle_standard_chat
from knowledge.service import knowledge_query_service
from planner.api import planner_agent_service
from product.model_config_service import (
    get_model_config_snapshot,
    list_model_provider_presets,
    model_config_service,
)
from shared import settings
from shared.config_contract import build_product_config_snapshot, validate_product_config
from shared.schemas import (
    AdminAuthLoginRequest,
    AdminAuthLoginResponse,
    AdminModelConfigResponse,
    AdminModelConfigTestRequest,
    AdminModelConfigTestResponse,
    AdminModelConfigUpdateRequest,
    AdminModelProviderPresetResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    PlannerTaskDetailResponse,
    PlannerTaskEventsResponse,
    PlannerTaskLocalResultRequest,
    PlannerTaskPermissionDecisionRequest,
    PlannerTaskResumeRequest,
    PlannerTaskSummaryResponse,
    ProductConfigSnapshotResponse,
    ProductConfigValidationResponse,
    SkillAcceptanceExampleResponse,
    SkillDefinitionResponse,
    SkillDraftCreateRequest,
    SkillDraftApprovalRequest,
    SkillDraftResponse,
    SkillDraftUpdateRequest,
    SkillParameterDefinitionResponse,
    SkillToolCallTemplateResponse,
    ToolDefinitionResponse,
)
from skills.registry import get_skill, list_skills
from skills.user_store import skill_draft_store


router = APIRouter()


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def client_ui() -> HTMLResponse:
    """Standalone client panel (hosts, tools and chat) served by the backend."""

    page = Path(__file__).resolve().parent / "ui.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))


@router.get("/connector/capabilities")
async def connector_capabilities():
    return build_connector_capabilities()


@router.get("/connector/diagnostics")
async def connector_diagnostics():
    return await build_connector_diagnostics()


@router.get("/hosts")
def list_hosts():
    """List external software hosts discovered via the Host Adapter Contract."""

    from host_mcp.runtime import HostMcpExecutor

    executor = HostMcpExecutor()
    return {
        "hosts": executor.hosts(),
        "tools": executor.tool_names(),
        "errors": executor.errors(),
    }


def require_admin_access(
    admin_token: str | None = Header(default=None, alias="X-AgentBridge-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> None:
    configured = settings.CADCOPILOT_ADMIN_TOKEN
    if not configured:
        return
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    if not hmac.compare_digest((admin_token or bearer or "").strip(), configured):
        raise HTTPException(status_code=401, detail="admin token is required")


@router.post("/admin/auth/login", response_model=AdminAuthLoginResponse)
async def admin_auth_login(request: AdminAuthLoginRequest) -> AdminAuthLoginResponse:
    username_ok = hmac.compare_digest((request.username or "").strip(), settings.CADCOPILOT_ADMIN_USERNAME)
    password_ok = hmac.compare_digest(request.password or "", settings.CADCOPILOT_ADMIN_PASSWORD)
    if not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="invalid admin username or password")
    return AdminAuthLoginResponse(
        access_token=settings.CADCOPILOT_ADMIN_TOKEN or "local-model-config-session",
        username=settings.CADCOPILOT_ADMIN_USERNAME,
        auth_configured=bool(settings.CADCOPILOT_ADMIN_USERNAME and settings.CADCOPILOT_ADMIN_PASSWORD),
    )


@router.get("/admin/model-presets", response_model=list[AdminModelProviderPresetResponse])
async def admin_model_presets(_: None = Depends(require_admin_access)):
    return list_model_provider_presets()


@router.get("/admin/model-config", response_model=AdminModelConfigResponse)
async def admin_model_config(_: None = Depends(require_admin_access)):
    return get_model_config_snapshot()


@router.put("/admin/model-config", response_model=AdminModelConfigResponse)
async def admin_update_model_config(request: AdminModelConfigUpdateRequest, _: None = Depends(require_admin_access)):
    try:
        return model_config_service.update_provider_config(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/admin/model-config/{provider}", response_model=AdminModelConfigResponse)
async def admin_delete_model_config(provider: str, _: None = Depends(require_admin_access)):
    try:
        return model_config_service.delete_provider_config(provider)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not configured" in str(exc) else 400, detail=str(exc)) from exc


@router.post("/admin/model-config/test", response_model=AdminModelConfigTestResponse)
async def admin_test_model_config(request: AdminModelConfigTestRequest, _: None = Depends(require_admin_access)):
    return model_config_service.test_provider_config(request.provider)


@router.get("/config/snapshot", response_model=ProductConfigSnapshotResponse)
async def config_snapshot():
    return build_product_config_snapshot()


@router.get("/config/validate", response_model=ProductConfigValidationResponse)
async def config_validate():
    return validate_product_config()


@router.post("/chat/message", response_model=ChatMessageResponse)
async def chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    if not request.message.strip() and not request.image_base64:
        raise HTTPException(status_code=400, detail="message or image_base64 is required")
    return await handle_agent_draw(request) if (request.mode or "").strip().lower() == "draw" else await handle_standard_chat(request)


@router.post("/knowledge/query", response_model=KnowledgeQueryResponse)
async def knowledge_query(request: KnowledgeQueryRequest):
    return await knowledge_query_service.query(request)


@router.get("/planner/tasks", response_model=list[PlannerTaskSummaryResponse])
async def list_planner_tasks(limit: int = 10, status: str | None = None):
    return planner_agent_service.list_recent_tasks(limit=limit, status_filter=status)


@router.get("/planner/tasks/{task_id}", response_model=PlannerTaskDetailResponse)
async def get_planner_task(task_id: str):
    task = planner_agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("/planner/tasks/{task_id}/events", response_model=PlannerTaskEventsResponse)
async def get_planner_task_events(task_id: str):
    events = planner_agent_service.get_task_events(task_id)
    if events is None:
        raise HTTPException(status_code=404, detail="task not found")
    return events


@router.post("/planner/tasks/{task_id}/cancel", response_model=PlannerTaskDetailResponse)
async def cancel_planner_task(task_id: str):
    task = planner_agent_service.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/planner/tasks/{task_id}/local-result", response_model=PlannerTaskDetailResponse)
async def record_planner_local_result(task_id: str, request: PlannerTaskLocalResultRequest):
    task = planner_agent_service.record_local_result(task_id, request)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/planner/tasks/{task_id}/permission-decision", response_model=PlannerTaskDetailResponse)
async def record_planner_permission_decision(task_id: str, request: PlannerTaskPermissionDecisionRequest):
    task = planner_agent_service.record_permission_decision(task_id, request)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/planner/tasks/{task_id}/resume", response_model=ChatMessageResponse)
async def resume_planner_task(task_id: str, request: PlannerTaskResumeRequest):
    response = await planner_agent_service.resume_task(task_id, request)
    if response is None:
        raise HTTPException(status_code=404, detail="task not resumable")
    return response


@router.post("/planner/tasks/{task_id}/retry", response_model=ChatMessageResponse)
async def retry_planner_task(task_id: str):
    response = await planner_agent_service.retry_task(task_id)
    if response is None:
        raise HTTPException(status_code=404, detail="task not retryable")
    return response


@router.post("/planner/tasks/{task_id}/skill-draft", response_model=SkillDraftResponse, status_code=201)
async def create_skill_draft_from_task(task_id: str):
    task = planner_agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    try:
        return skill_draft_store.create_from_task(task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/planner/skill-drafts", response_model=list[SkillDraftResponse])
async def list_skill_drafts():
    return skill_draft_store.list()


@router.post("/planner/skill-drafts", response_model=SkillDraftResponse, status_code=201)
async def create_skill_draft(request: SkillDraftCreateRequest):
    try:
        return skill_draft_store.create(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/planner/skill-drafts/{skill_id}", response_model=SkillDraftResponse)
async def get_skill_draft(skill_id: str):
    draft = skill_draft_store.get(skill_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Skill draft not found")
    return draft


@router.put("/planner/skill-drafts/{skill_id}", response_model=SkillDraftResponse)
async def update_skill_draft(skill_id: str, request: SkillDraftUpdateRequest):
    try:
        return skill_draft_store.update(skill_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/planner/skill-drafts/{skill_id}/validate", response_model=SkillDraftResponse)
async def validate_skill_draft(skill_id: str):
    try:
        return skill_draft_store.validate(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/planner/skill-drafts/{skill_id}/approve", response_model=SkillDraftResponse)
async def approve_skill_draft(skill_id: str, request: SkillDraftApprovalRequest):
    try:
        return skill_draft_store.approve(skill_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _skill_response(skill) -> SkillDefinitionResponse:
    return SkillDefinitionResponse(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        category=skill.category,
        mcp_tools=list(skill.mcp_tools),
        auto_tool_calls=[SkillToolCallTemplateResponse(tool_name=item.tool_name, arguments=dict(item.arguments)) for item in skill.auto_tool_calls],
        parameters=[SkillParameterDefinitionResponse(name=item.name, label=item.label, value_type=item.value_type, required=item.required, default_value=item.default_value, options=list(item.options), description=item.description) for item in skill.parameters],
        planner_hints=list(skill.planner_hints),
        examples=list(skill.examples),
        acceptance_examples=[SkillAcceptanceExampleResponse(title=item.title, user_message=item.user_message, expected_behavior=item.expected_behavior, manual_test=item.manual_test) for item in skill.acceptance_examples],
        enabled=skill.enabled,
    )


@router.get("/planner/skills", response_model=list[SkillDefinitionResponse])
async def list_planner_skills(enabled_only: bool = True):
    return [_skill_response(skill) for skill in list_skills(enabled_only=enabled_only)]


@router.get("/planner/skills/{skill_id}", response_model=SkillDefinitionResponse)
async def get_planner_skill(skill_id: str):
    skill = get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return _skill_response(skill)


def _tool_response(tool) -> ToolDefinitionResponse:
    return ToolDefinitionResponse(
        tool_name=tool.tool_name,
        display_name=tool.display_name,
        category=tool.category,
        description=tool.description,
        input_schema=dict(tool.input_schema),
        dry_run_supported=tool.dry_run_supported,
        side_effect_level=tool.side_effect_level,
        result_schema=dict(tool.result_schema),
    )


@router.get("/planner/tools", response_model=list[ToolDefinitionResponse])
async def list_planner_tools():
    return [_tool_response(tool) for tool in list_product_tools()]


@router.get("/planner/tools/{tool_name}", response_model=ToolDefinitionResponse)
async def get_planner_tool(tool_name: str):
    tool = get_product_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return _tool_response(tool)
