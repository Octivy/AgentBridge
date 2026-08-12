from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class ChatMessageRequest(BaseModel):
    message: str = Field(default="")
    image_base64: Optional[str] = None
    mode: str = Field(default="draw")
    user_id: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    protocol: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    planner_session_id: Optional[str] = None
    trace_id: Optional[str] = None
    agent_approval: Optional[str] = None
    response_schema: Optional[Dict[str, Any]] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    knowledge_mode: str = Field(default="auto")


class DrawCommand(BaseModel):
    type: str
    layer: Optional[str] = None
    color: Optional[int] = None
    start: Optional[List[float]] = None
    end: Optional[List[float]] = None
    center: Optional[List[float]] = None
    radius: Optional[float] = None
    startAngle: Optional[float] = None
    endAngle: Optional[float] = None
    points: Optional[List[List[float]]] = None
    closed: Optional[bool] = None
    content: Optional[str] = None
    position: Optional[List[float]] = None
    height: Optional[float] = None


class PlannerExecutionEvent(BaseModel):
    tool_name: str
    status: str
    summary: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HarnessEventResponse(BaseModel):
    event_id: str
    session_id: str
    task_id: str
    event_type: str
    sequence: int
    timestamp: str
    summary: str = ""
    step_id: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    visible_to_user: bool = True
    collapse_default: bool = False
    trace_id: Optional[str] = None


class PlannerTaskEventsResponse(BaseModel):
    task_id: str
    events: List[HarnessEventResponse] = Field(default_factory=list)


class PlannerState(BaseModel):
    trace_id: Optional[str] = None
    task_status: Optional[str] = None
    agent_approval: str = "annotate"
    pending_permission_action: Optional[str] = None
    permission_summary: Optional[str] = None
    executed_tools: List[str] = Field(default_factory=list)
    selected_skills: List[str] = Field(default_factory=list)
    execution_events: List[PlannerExecutionEvent] = Field(default_factory=list)
    completed_steps: List[str] = Field(default_factory=list)
    pending_steps: List[str] = Field(default_factory=list)
    ask_user_type: Optional[str] = None
    ask_user_hint: Optional[str] = None


class PlannerTaskErrorResponse(BaseModel):
    code: str
    message: str
    technical_detail: Optional[str] = None


class PlannerTaskLocalResultRequest(BaseModel):
    status: str = Field(default="completed")
    message: str = Field(default="")
    affected_entities_count: int = 0
    trace_id: Optional[str] = None
    tool_name: str = Field(default="local_apply_preview")
    details: Dict[str, Any] = Field(default_factory=dict)


class PlannerTaskPermissionDecisionRequest(BaseModel):
    decision: str = Field(default="deny")
    message: str = Field(default="")
    trace_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    reply_text: str
    commands: List[DrawCommand] = Field(default_factory=list)
    legacy_fallback_used: bool = False
    planner_session_id: Optional[str] = None
    trace_id: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    planner_state: Optional[PlannerState] = None
    task_status: Optional[str] = None
    executed_tools: List[str] = Field(default_factory=list)
    selected_skills: List[str] = Field(default_factory=list)
    execution_events: List[PlannerExecutionEvent] = Field(default_factory=list)
    planner_completed_steps: List[str] = Field(default_factory=list)
    planner_pending_steps: List[str] = Field(default_factory=list)
    ask_user_type: Optional[str] = None
    ask_user_hint: Optional[str] = None
    knowledge_grounded: bool = False
    knowledge_citations: List["KnowledgeCitationResponse"] = Field(default_factory=list)
    knowledge_warning: str = ""

    @model_validator(mode="after")
    def sync_planner_state(self) -> "ChatMessageResponse":
        merged_planner_state = PlannerState(
            trace_id=(self.planner_state.trace_id if self.planner_state and self.planner_state.trace_id is not None else self.trace_id),
            task_status=(self.planner_state.task_status if self.planner_state and self.planner_state.task_status is not None else self.task_status),
            agent_approval=(self.planner_state.agent_approval if self.planner_state else "annotate"),
            pending_permission_action=(self.planner_state.pending_permission_action if self.planner_state else None),
            permission_summary=(self.planner_state.permission_summary if self.planner_state else None),
            executed_tools=list(self.planner_state.executed_tools) if self.planner_state and self.planner_state.executed_tools else list(self.executed_tools),
            selected_skills=list(self.planner_state.selected_skills) if self.planner_state and self.planner_state.selected_skills else list(self.selected_skills),
            execution_events=list(self.planner_state.execution_events) if self.planner_state and self.planner_state.execution_events else list(self.execution_events),
            completed_steps=list(self.planner_state.completed_steps) if self.planner_state and self.planner_state.completed_steps else list(self.planner_completed_steps),
            pending_steps=list(self.planner_state.pending_steps) if self.planner_state and self.planner_state.pending_steps else list(self.planner_pending_steps),
            ask_user_type=(self.planner_state.ask_user_type if self.planner_state and self.planner_state.ask_user_type is not None else self.ask_user_type),
            ask_user_hint=(self.planner_state.ask_user_hint if self.planner_state and self.planner_state.ask_user_hint is not None else self.ask_user_hint),
        )

        has_planner_payload = (
            merged_planner_state.task_status is not None
            or merged_planner_state.trace_id is not None
            or bool(merged_planner_state.executed_tools)
            or bool(merged_planner_state.selected_skills)
            or bool(merged_planner_state.execution_events)
            or bool(merged_planner_state.completed_steps)
            or bool(merged_planner_state.pending_steps)
            or merged_planner_state.ask_user_type is not None
            or merged_planner_state.ask_user_hint is not None
            or merged_planner_state.pending_permission_action is not None
            or merged_planner_state.permission_summary is not None
        )

        self.planner_state = merged_planner_state if has_planner_payload else None
        if self.planner_state is not None:
            self.trace_id = self.planner_state.trace_id
            self.task_status = self.planner_state.task_status
            self.executed_tools = list(self.planner_state.executed_tools)
            self.selected_skills = list(self.planner_state.selected_skills)
            self.execution_events = list(self.planner_state.execution_events)
            self.planner_completed_steps = list(self.planner_state.completed_steps)
            self.planner_pending_steps = list(self.planner_state.pending_steps)
            self.ask_user_type = self.planner_state.ask_user_type
            self.ask_user_hint = self.planner_state.ask_user_hint

        return self


class PlannerTaskSummaryResponse(BaseModel):
    task_id: str
    trace_id: Optional[str] = None
    user_goal: str
    task_status: str
    last_user_message: str = ""
    active_step: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resumable: bool = False
    retryable: bool = False
    cancellable: bool = False
    last_error: Optional[PlannerTaskErrorResponse] = None


class PlannerTaskDetailResponse(PlannerTaskSummaryResponse):
    final_response: str = ""
    planner_state: Optional[PlannerState] = None


class SkillToolCallTemplateResponse(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class SkillParameterDefinitionResponse(BaseModel):
    name: str
    label: str
    value_type: str = "string"
    required: bool = True
    default_value: str = ""
    options: List[str] = Field(default_factory=list)
    description: str = ""


class SkillAcceptanceExampleResponse(BaseModel):
    title: str
    user_message: str
    expected_behavior: str
    manual_test: bool = False


class SkillDefinitionResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    category: str
    mcp_tools: List[str] = Field(default_factory=list)
    auto_tool_calls: List[SkillToolCallTemplateResponse] = Field(default_factory=list)
    parameters: List[SkillParameterDefinitionResponse] = Field(default_factory=list)
    planner_hints: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    acceptance_examples: List[SkillAcceptanceExampleResponse] = Field(default_factory=list)
    enabled: bool = True


class SkillDraftCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="user", max_length=80)
    user_goal: str = Field(default="", max_length=2000)
    plan_steps: List[str] = Field(default_factory=list)
    mcp_tools: List[str] = Field(default_factory=list)
    source_task_id: Optional[str] = None
    source_trace_id: Optional[str] = None
    source_skill_ids: List[str] = Field(default_factory=list)


class SkillDraftUpdateRequest(SkillDraftCreateRequest):
    pass


class SkillDraftApprovalRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = Field(default="", max_length=1000)


class SkillDraftResponse(BaseModel):
    skill_id: str
    version: int = 1
    status: str = "draft"
    name: str
    description: str = ""
    category: str = "user"
    user_goal: str = ""
    plan_steps: List[str] = Field(default_factory=list)
    mcp_tools: List[str] = Field(default_factory=list)
    source_task_id: Optional[str] = None
    source_trace_id: Optional[str] = None
    source_skill_ids: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    review_required: bool = True
    validation_errors: List[str] = Field(default_factory=list)
    reviewer: Optional[str] = None
    review_note: str = ""
    reviewed_at: Optional[datetime] = None
    enabled: bool = False


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    protocol: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    max_sources: int = Field(default=5, ge=1, le=8)
    trace_id: Optional[str] = None


class KnowledgeCitationResponse(BaseModel):
    citation_id: str
    title: str
    source: str
    section: str = ""
    version: str = ""
    excerpt: str
    score: float


class KnowledgeQueryResponse(BaseModel):
    answer: str = ""
    citations: List[KnowledgeCitationResponse] = Field(default_factory=list)
    grounded: bool = False
    warning: str = ""
    trace_id: str
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


class ToolDefinitionResponse(BaseModel):
    tool_name: str
    display_name: str
    category: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    dry_run_supported: bool
    side_effect_level: str
    result_schema: dict = Field(default_factory=dict)


class PlannerTaskResumeRequest(BaseModel):
    message: str = Field(default="")


class ProductConfigFieldResponse(BaseModel):
    key: str
    owner: str
    source: str
    category: str
    configured: bool = False
    sensitive: bool = False
    value: Optional[str] = None
    description: str = ""


class ProductConfigSnapshotResponse(BaseModel):
    environment: str = "local"
    plugin_config_file: str = "agentbridge.config.json"
    plugin_env_prefix: str = "CADCOPILOT_"
    backend_fields: List[ProductConfigFieldResponse] = Field(default_factory=list)
    plugin_fields: List[ProductConfigFieldResponse] = Field(default_factory=list)
    sensitive_keys: List[str] = Field(default_factory=list)


class ProductConfigValidationIssueResponse(BaseModel):
    key: str
    owner: str
    severity: str
    message: str


class ProductConfigValidationResponse(BaseModel):
    ok: bool = True
    issues: List[ProductConfigValidationIssueResponse] = Field(default_factory=list)


class AdminAuthLoginRequest(BaseModel):
    username: str
    password: str


class AdminAuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "admin"
    username: str
    auth_configured: bool = False


class AdminModelProviderPresetResponse(BaseModel):
    provider: str
    display_name: str
    description: str = ""
    default_base_url: str = ""
    default_model: str = ""
    api_key_hint: str = ""
    supports_openai_compatible: bool = True


class AdminModelProviderConfigRequest(BaseModel):
    provider: str
    display_name: Optional[str] = None
    api_base_url: str
    model: str
    api_key: Optional[str] = None
    enabled: bool = True
    protocol: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)


class AdminModelProviderConfigResponse(BaseModel):
    provider: str
    display_name: str
    api_base_url: str = ""
    model: str = ""
    enabled: bool = False
    api_key_configured: bool = False
    api_key_mask: str = ""
    updated_at: Optional[datetime] = None
    validation_status: str = "unknown"
    validation_messages: List[str] = Field(default_factory=list)
    protocol: str = ""
    capabilities: List[str] = Field(default_factory=list)


class AdminModelConfigResponse(BaseModel):
    active_provider: str = ""
    providers: List[AdminModelProviderConfigResponse] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
    updated_by: str = ""
    persistence_enabled: bool = False
    persistence_path: str = ""


class AdminModelConfigUpdateRequest(BaseModel):
    active_provider: str
    provider_config: AdminModelProviderConfigRequest
    updated_by: str = "admin"


class AdminModelConfigTestRequest(BaseModel):
    provider: Optional[str] = None


class AdminValidationCheckResponse(BaseModel):
    severity: str
    message: str


class AdminModelConfigTestResponse(BaseModel):
    ok: bool
    provider: str
    display_name: str = ""
    checks: List[AdminValidationCheckResponse] = Field(default_factory=list)
