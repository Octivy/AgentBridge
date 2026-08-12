using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace AgentBridge.LLM
{
    public class SkillParameterDefinitionResponse
    {
        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("label")]
        public string Label { get; set; }

        [JsonProperty("value_type")]
        public string ValueType { get; set; }

        [JsonProperty("required")]
        public bool Required { get; set; }

        [JsonProperty("default_value")]
        public string DefaultValue { get; set; }

        [JsonProperty("options")]
        public System.Collections.Generic.List<string> Options { get; set; }

        [JsonProperty("description")]
        public string Description { get; set; }
    }

    public class SkillAcceptanceExampleResponse
    {
        [JsonProperty("title")]
        public string Title { get; set; }

        [JsonProperty("user_message")]
        public string UserMessage { get; set; }

        [JsonProperty("expected_behavior")]
        public string ExpectedBehavior { get; set; }

        [JsonProperty("manual_test")]
        public bool ManualTest { get; set; }
    }

    public class SkillToolCallTemplateResponse
    {
        [JsonProperty("tool_name")]
        public string ToolName { get; set; }

        [JsonProperty("arguments")]
        public JObject Arguments { get; set; }
    }

    public class SkillDefinitionResponse
    {
        [JsonProperty("skill_id")]
        public string SkillId { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("description")]
        public string Description { get; set; }

        [JsonProperty("category")]
        public string Category { get; set; }

        [JsonProperty("mcp_tools")]
        public System.Collections.Generic.List<string> McpTools { get; set; }

        [JsonProperty("auto_tool_calls")]
        public System.Collections.Generic.List<SkillToolCallTemplateResponse> AutoToolCalls { get; set; }

        [JsonProperty("parameters")]
        public System.Collections.Generic.List<SkillParameterDefinitionResponse> Parameters { get; set; }

        [JsonProperty("planner_hints")]
        public System.Collections.Generic.List<string> PlannerHints { get; set; }

        [JsonProperty("examples")]
        public System.Collections.Generic.List<string> Examples { get; set; }

        [JsonProperty("acceptance_examples")]
        public System.Collections.Generic.List<SkillAcceptanceExampleResponse> AcceptanceExamples { get; set; }

        [JsonProperty("enabled")]
        public bool Enabled { get; set; }
    }

    public class SkillDraftResponse
    {
        [JsonProperty("skill_id")]
        public string SkillId { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("review_required")]
        public bool ReviewRequired { get; set; }

        [JsonProperty("source_task_id")]
        public string SourceTaskId { get; set; }

        [JsonProperty("mcp_tools")]
        public System.Collections.Generic.List<string> McpTools { get; set; }
    }

    public class PlannerExecutionEventResponse
    {
        [JsonProperty("tool_name")]
        public string ToolName { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("summary")]
        public string Summary { get; set; }

        [JsonProperty("request_id")]
        public string RequestId { get; set; }

        [JsonProperty("trace_id")]
        public string TraceId { get; set; }

        [JsonProperty("error_code")]
        public string ErrorCode { get; set; }

        [JsonProperty("details")]
        public JObject Details { get; set; }
    }

    public class HarnessEventResponse
    {
        [JsonProperty("event_id")]
        public string EventId { get; set; }

        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("task_id")]
        public string TaskId { get; set; }

        [JsonProperty("event_type")]
        public string EventType { get; set; }

        [JsonProperty("sequence")]
        public int Sequence { get; set; }

        [JsonProperty("timestamp")]
        public string Timestamp { get; set; }

        [JsonProperty("summary")]
        public string Summary { get; set; }

        [JsonProperty("step_id")]
        public string StepId { get; set; }

        [JsonProperty("payload")]
        public JObject Payload { get; set; }

        [JsonProperty("visible_to_user")]
        public bool VisibleToUser { get; set; } = true;

        [JsonProperty("collapse_default")]
        public bool CollapseDefault { get; set; }

        [JsonProperty("trace_id")]
        public string TraceId { get; set; }
    }

    public class PlannerTaskEventsResponse
    {
        [JsonProperty("task_id")]
        public string TaskId { get; set; }

        [JsonProperty("events")]
        public System.Collections.Generic.List<HarnessEventResponse> Events { get; set; }
    }

    public class PlannerStateResponse
    {
        [JsonProperty("trace_id")]
        public string TraceId { get; set; }

        [JsonProperty("task_status")]
        public string TaskStatus { get; set; }

        [JsonProperty("agent_approval")]
        public string AgentApproval { get; set; }

        [JsonProperty("pending_permission_action")]
        public string PendingPermissionAction { get; set; }

        [JsonProperty("permission_summary")]
        public string PermissionSummary { get; set; }

        [JsonProperty("executed_tools")]
        public System.Collections.Generic.List<string> ExecutedTools { get; set; }

        [JsonProperty("selected_skills")]
        public System.Collections.Generic.List<string> SelectedSkills { get; set; }

        [JsonProperty("execution_events")]
        public System.Collections.Generic.List<PlannerExecutionEventResponse> ExecutionEvents { get; set; }

        [JsonProperty("completed_steps")]
        public System.Collections.Generic.List<string> CompletedSteps { get; set; }

        [JsonProperty("pending_steps")]
        public System.Collections.Generic.List<string> PendingSteps { get; set; }

        [JsonProperty("ask_user_type")]
        public string AskUserType { get; set; }

        [JsonProperty("ask_user_hint")]
        public string AskUserHint { get; set; }
    }

    public class LlmRequest
    {
        [JsonProperty("message")]
        public string Message { get; set; }

        [JsonProperty("image_base64")]
        public string ImageBase64 { get; set; }

        [JsonProperty("mode")]
        public string Mode { get; set; }

        [JsonProperty("user_id")]
        public string UserId { get; set; }

        [JsonProperty("model")]
        public string Model { get; set; }

        [JsonProperty("provider")]
        public string Provider { get; set; }

        [JsonProperty("api_key")]
        public string ApiKey { get; set; }

        [JsonProperty("api_base_url")]
        public string ApiBaseUrl { get; set; }

        [JsonProperty("planner_session_id")]
        public string PlannerSessionId { get; set; }

        [JsonProperty("trace_id")]
        public string TraceId { get; set; }

        [JsonProperty("agent_approval")]
        public string AgentApproval { get; set; }
    }

    public class LlmTextResponse
    {
        [JsonProperty("reply_text")]
        public string ReplyText { get; set; }

        [JsonProperty("commands")]
        public System.Collections.Generic.List<DrawCommand> Commands { get; set; }

        [JsonProperty("legacy_fallback_used")]
        public bool LegacyFallbackUsed { get; set; }

        [JsonProperty("planner_session_id")]
        public string PlannerSessionId { get; set; }

        [JsonProperty("trace_id")]
        public string TraceId { get; set; }

        [JsonProperty("model_provider")]
        public string ModelProvider { get; set; }

        [JsonProperty("model_name")]
        public string ModelName { get; set; }

        [JsonProperty("planner_state")]
        public PlannerStateResponse PlannerState { get; set; }

        [JsonProperty("task_status")]
        public string TaskStatus { get; set; }

        [JsonProperty("executed_tools")]
        public System.Collections.Generic.List<string> ExecutedTools { get; set; }

        [JsonProperty("selected_skills")]
        public System.Collections.Generic.List<string> SelectedSkills { get; set; }

        [JsonProperty("execution_events")]
        public System.Collections.Generic.List<PlannerExecutionEventResponse> ExecutionEvents { get; set; }

        [JsonProperty("planner_completed_steps")]
        public System.Collections.Generic.List<string> PlannerCompletedSteps { get; set; }

        [JsonProperty("planner_pending_steps")]
        public System.Collections.Generic.List<string> PlannerPendingSteps { get; set; }

        [JsonProperty("ask_user_type")]
        public string AskUserType { get; set; }

        [JsonProperty("ask_user_hint")]
        public string AskUserHint { get; set; }
    }

    public class PlannerTaskErrorResponse
    {
        [JsonProperty("code")]
        public string Code { get; set; }

        [JsonProperty("message")]
        public string Message { get; set; }

        [JsonProperty("technical_detail")]
        public string TechnicalDetail { get; set; }
    }

    public class PlannerTaskSummaryResponse
    {
        [JsonProperty("task_id")]
        public string TaskId { get; set; }

        [JsonProperty("trace_id")]
        public string TraceId { get; set; }

        [JsonProperty("user_goal")]
        public string UserGoal { get; set; }

        [JsonProperty("task_status")]
        public string TaskStatus { get; set; }

        [JsonProperty("last_user_message")]
        public string LastUserMessage { get; set; }

        [JsonProperty("active_step")]
        public string ActiveStep { get; set; }

        [JsonProperty("created_at")]
        public string CreatedAt { get; set; }

        [JsonProperty("updated_at")]
        public string UpdatedAt { get; set; }

        [JsonProperty("resumable")]
        public bool Resumable { get; set; }

        [JsonProperty("retryable")]
        public bool Retryable { get; set; }

        [JsonProperty("cancellable")]
        public bool Cancellable { get; set; }

        [JsonProperty("last_error")]
        public PlannerTaskErrorResponse LastError { get; set; }
    }

    public class PlannerTaskDetailResponse : PlannerTaskSummaryResponse
    {
        [JsonProperty("final_response")]
        public string FinalResponse { get; set; }

        [JsonProperty("planner_state")]
        public PlannerStateResponse PlannerState { get; set; }
    }
}
