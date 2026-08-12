"""HTTP surface for the CAD/MCP MVP."""

import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse

from cadmcp.tool_registry import get_product_tool, list_product_tools
from connector_runtime.diagnostics import build_connector_capabilities, build_connector_diagnostics
from adapter_install.sketchup import install_sketchup_extension, sketchup_extension_status
from adapter_install.blender import blender_addon_status, install_blender_addon
from adapter_install.rhino import install_rhino_adapter, rhino_adapter_status
from agent.host_task import AgentTaskRequest, run_host_task
from delivery.models import DeliverableCreate, DeliveryTaskView, HandoffUpdate
from delivery.service import delivery_service
from host_config.models import (
    HostAdapterConfig,
    HostConfigCreate,
    HostConfigStatus,
    HostConfigUpdate,
    HostTestResult,
)
from host_config.service import host_config_service
from http_api.agent_handler import handle_agent_draw
from http_api.chat_handler import handle_standard_chat
from knowledge.service import knowledge_query_service
from mcp_registry.models import (
    McpPreviewResponse,
    McpStatusResponse,
    McpWriteRequest,
    McpWriteResult,
)
from mcp_registry.service import (
    build_claude_json,
    build_mcp_servers,
    codex_config_path,
    render_codex_toml,
    write_claude_config,
    write_codex_config,
)
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


@router.post("/agent/task")
async def run_agent_task(request: AgentTaskRequest) -> dict:
    """让 Agent 用宿主工具自动完成一个任务（需求拆解 -> 执行 -> 交付记录）。"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    try:
        return await run_host_task(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


# ----- 配置中心：软件(Host)适配器管理 -----


@router.get("/config/hosts", response_model=list[HostConfigStatus])
def list_host_configs():
    """List configured software bridges with live status."""

    return host_config_service.list_status()


@router.post("/config/hosts", response_model=HostAdapterConfig, status_code=201)
def create_host_config(request: HostConfigCreate) -> HostAdapterConfig:
    try:
        return host_config_service.create_config(request)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 400, detail=str(exc)) from exc


@router.put("/config/hosts/{host_id}", response_model=HostAdapterConfig)
def update_host_config(host_id: str, request: HostConfigUpdate) -> HostAdapterConfig:
    try:
        return host_config_service.update_config(host_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/config/hosts/{host_id}", status_code=204)
def delete_host_config(host_id: str) -> None:
    if not host_config_service.delete_config(host_id):
        raise HTTPException(status_code=404, detail=f"host config not found: {host_id}")


@router.post("/config/hosts/{host_id}/test", response_model=HostTestResult)
def test_host_config(host_id: str) -> HostTestResult:
    try:
        return host_config_service.test(host_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/config/hosts/{host_id}/start", response_model=HostConfigStatus)
def start_host_config(host_id: str) -> HostConfigStatus:
    try:
        return host_config_service.start(host_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/config/hosts/{host_id}/stop", response_model=HostConfigStatus)
def stop_host_config(host_id: str) -> HostConfigStatus:
    try:
        return host_config_service.stop(host_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/config/hosts/{host_id}/status", response_model=HostConfigStatus)
def host_config_status(host_id: str) -> HostConfigStatus:
    try:
        return host_config_service.status(host_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/config/hosts/auto-start", response_model=list[HostConfigStatus])
def auto_start_host_configs() -> list[HostConfigStatus]:
    """Start every enabled host marked auto_start (called by the desktop client on boot)."""

    return host_config_service.auto_start()


@router.post("/config/hosts/sketchup/install-extension")
def install_sketchup_extension_route() -> dict:
    """一键安装 AgentBridge 扩展到本机 SketchUp（重启 SketchUp 生效）。"""

    return install_sketchup_extension()


@router.get("/config/hosts/sketchup/extension-status")
def sketchup_extension_status_route() -> dict:
    """查询 AgentBridge 扩展在本机 SketchUp 的安装状态。"""

    return sketchup_extension_status()


@router.post("/config/hosts/blender/install-addon")
def install_blender_addon_route() -> dict:
    """一键安装 AgentBridge Blender 插件（重新打开 Blender 自动连接）。"""

    return install_blender_addon()


@router.get("/config/hosts/blender/addon-status")
def blender_addon_status_route() -> dict:
    """查询 AgentBridge Blender 插件安装状态。"""

    return blender_addon_status()


@router.post("/config/hosts/rhino/install-adapter")
def install_rhino_adapter_route() -> dict:
    """一键安装 AgentBridge Rhino 适配器（Rhino 重装后验证自动启动）。"""

    return install_rhino_adapter()


@router.get("/config/hosts/rhino/adapter-status")
def rhino_adapter_status_route() -> dict:
    """查询 AgentBridge Rhino 适配器安装状态。"""

    return rhino_adapter_status()


# ----- Agent 接入（MCP 注册管理） -----


@router.get("/config/mcp/preview", response_model=McpPreviewResponse)
def mcp_config_preview() -> McpPreviewResponse:
    """Preview the MCP server config that would be written for agents."""

    entries = build_mcp_servers()
    return McpPreviewResponse(
        servers=entries,
        codex_toml=render_codex_toml(entries),
        claude_json=build_claude_json(entries),
    )


@router.post("/config/mcp/codex", response_model=McpWriteResult)
def mcp_write_codex(request: McpWriteRequest) -> McpWriteResult:
    """Merge MCP servers into the user-level Codex config (~/.codex/config.toml)."""

    target = Path(request.target_path) if request.target_path else None
    result = write_codex_config(build_mcp_servers(), target=target)
    return McpWriteResult(**result)


@router.post("/config/mcp/claude", response_model=McpWriteResult)
def mcp_write_claude(request: McpWriteRequest) -> McpWriteResult:
    """Write the Claude Code project `.mcp.json` (existing file is backed up)."""

    target = Path(request.target_path) if request.target_path else None
    result = write_claude_config(build_mcp_servers(), target=target)
    return McpWriteResult(**result)


@router.get("/config/mcp/status", response_model=McpStatusResponse)
def mcp_config_status() -> McpStatusResponse:
    """Report which MCP servers are already registered in Codex vs generated."""

    path = codex_config_path()
    codex_servers: list[str] = []
    if path.exists():
        try:
            import tomllib

            data = tomllib.loads(path.read_text(encoding="utf-8"))
            codex_servers = sorted((data.get("mcp_servers") or {}).keys())
        except (OSError, tomllib.TOMLDecodeError):
            pass
    generated = [entry.name for entry in build_mcp_servers()]
    return McpStatusResponse(
        codex_path=str(path),
        codex_servers=codex_servers,
        generated_servers=generated,
    )


# ----- 任务交付（交付物 + 交接总结） -----


@router.get("/delivery/tasks", response_model=list[DeliveryTaskView])
def list_delivery_tasks(limit: int = 20) -> list[DeliveryTaskView]:
    return delivery_service.list(limit=limit)


@router.get("/delivery/tasks/{task_id}", response_model=DeliveryTaskView)
def get_delivery_task(task_id: str) -> DeliveryTaskView:
    view = delivery_service.get(task_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"delivery not found: {task_id}")
    return view


@router.post("/delivery/tasks/{task_id}/deliverables", response_model=DeliveryTaskView, status_code=201)
def add_deliverable(task_id: str, request: DeliverableCreate) -> DeliveryTaskView:
    try:
        return delivery_service.add_deliverable(task_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/delivery/tasks/{task_id}/handoff", response_model=DeliveryTaskView)
def update_handoff(task_id: str, request: HandoffUpdate) -> DeliveryTaskView:
    return delivery_service.set_handoff(task_id, request)


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
