using System.Collections.Generic;
using Newtonsoft.Json;

namespace AgentBridge.LLM
{
    public class DrawCommandResponse
    {
        [JsonProperty("commands")]
        public List<DrawCommand> Commands { get; set; }

        [JsonProperty("explanation")]
        public string Explanation { get; set; }

        [JsonProperty("reply_text")]
        public string ReplyText { get; set; }

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
        public List<string> ExecutedTools { get; set; }

        [JsonProperty("selected_skills")]
        public List<string> SelectedSkills { get; set; }

        [JsonProperty("execution_events")]
        public List<PlannerExecutionEventResponse> ExecutionEvents { get; set; }

        [JsonProperty("harness_events")]
        public List<HarnessEventResponse> HarnessEvents { get; set; }

        [JsonProperty("planner_completed_steps")]
        public List<string> PlannerCompletedSteps { get; set; }

        [JsonProperty("planner_pending_steps")]
        public List<string> PlannerPendingSteps { get; set; }

        [JsonProperty("ask_user_type")]
        public string AskUserType { get; set; }

        [JsonProperty("ask_user_hint")]
        public string AskUserHint { get; set; }

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

    public class DrawCommand
    {
        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("layer")]
        public string Layer { get; set; }

        [JsonProperty("color")]
        public int? Color { get; set; }

        [JsonProperty("start")]
        public double[] Start { get; set; }

        [JsonProperty("end")]
        public double[] End { get; set; }

        [JsonProperty("center")]
        public double[] Center { get; set; }

        [JsonProperty("radius")]
        public double? Radius { get; set; }

        [JsonProperty("startAngle")]
        public double? StartAngle { get; set; }

        [JsonProperty("endAngle")]
        public double? EndAngle { get; set; }

        [JsonProperty("points")]
        public double[][] Points { get; set; }

        [JsonProperty("closed")]
        public bool? Closed { get; set; }

        [JsonProperty("content")]
        public string Content { get; set; }

        [JsonProperty("position")]
        public double[] Position { get; set; }

        [JsonProperty("height")]
        public double? Height { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("rotation")]
        public double? Rotation { get; set; }

        [JsonProperty("scale")]
        public double? Scale { get; set; }

        [JsonProperty("offset")]
        public double? Offset { get; set; }

        [JsonProperty("pattern")]
        public string Pattern { get; set; }

        [JsonProperty("boundary")]
        public double[][] Boundary { get; set; }
    }
}
