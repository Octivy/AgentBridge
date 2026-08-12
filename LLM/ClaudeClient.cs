using System;
using System.IO;
using System.Net.Http;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using AgentBridge.Core;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Globalization;
using System.Collections.Generic;

namespace AgentBridge.LLM
{
    public class ClaudeClient
    {
        private const string ProviderAnthropic = "anthropic";
        private const string ProviderOpenAi = "openai";
        private const string ProviderDeepSeek = "deepseek";
        private const string ProviderMiniMax = "minimax";
        private const string ProviderCadCopilot = "cadcopilot";
        private const string ProviderOpenAiCompatible = "openai_compatible";
        private const string ProviderOllama = "ollama";
        private const string ProviderEnterprisePrivate = "enterprise_private";

        private static readonly HttpClient HttpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };

        private readonly string _serviceBaseUrl;
        private readonly string _connectionMode;
        private readonly string _claudeApiKey;
        private readonly string _claudeModel;
        private readonly string _openAiApiKey;
        private readonly string _openAiApiBaseUrl;
        private readonly string _openAiModel;
        private readonly string _directProvider;
        private readonly string _serviceModel;
        private readonly string _agentApproval;
        private readonly string _systemPrompt;
        private string _plannerSessionId;

        public ClaudeClient()
        {
            _serviceBaseUrl = Config.Get("CADCOPILOT_API_BASE_URL", string.Empty).Trim();
            _connectionMode = NormalizeConnectionMode(Config.Get("CADCOPILOT_CONNECTION_MODE", string.Empty), _serviceBaseUrl);
            _directProvider = NormalizeProvider(Config.Get("LLM_PROVIDER", ProviderMiniMax));
            _claudeApiKey = Config.Get("OPENAI_API_KEY", Config.Get("CLAUDE_API_KEY", string.Empty)).Trim();
            _claudeModel = Config.Get("OPENAI_MODEL", Config.Get("CLAUDE_MODEL", GetDefaultProviderModel(ProviderAnthropic))).Trim();
            _openAiApiKey = Config.Get("OPENAI_API_KEY", string.Empty).Trim();
            _openAiApiBaseUrl = Config.Get("OPENAI_API_BASE_URL", GetDefaultProviderBaseUrl(_directProvider)).Trim();
            _openAiModel = Config.Get("OPENAI_MODEL", GetDefaultProviderModel(_directProvider)).Trim();
            _serviceModel = Config.Get("CADCOPILOT_MODEL", "MiniMax-M2.7").Trim();
            _agentApproval = NormalizeAgentApproval(Config.Get("CADCOPILOT_AGENT_APPROVAL", "annotate"));
            _systemPrompt = LoadSystemPrompt();
            _plannerSessionId = string.Empty;
        }

        public ClaudeClient(string connectionMode, string serviceBaseUrl, string directProvider, string openAiApiKey, string openAiApiBaseUrl, string openAiModel)
        {
            string normalizedProvider = NormalizeProvider(directProvider ?? ProviderMiniMax);
            _serviceBaseUrl = (serviceBaseUrl ?? string.Empty).Trim();
            _connectionMode = NormalizeConnectionMode(connectionMode ?? string.Empty, _serviceBaseUrl);
            _claudeApiKey = string.Equals(normalizedProvider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase) ? (openAiApiKey ?? string.Empty).Trim() : string.Empty;
            _claudeModel = string.Equals(normalizedProvider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(openAiModel) ? openAiModel.Trim() : "claude-sonnet-4-20250514";
            _openAiApiKey = (openAiApiKey ?? string.Empty).Trim();
            _openAiApiBaseUrl = (openAiApiBaseUrl ?? string.Empty).Trim();
            _openAiModel = (openAiModel ?? string.Empty).Trim();
            _directProvider = normalizedProvider;
            _serviceModel = _openAiModel;
            _agentApproval = NormalizeAgentApproval(Config.Get("CADCOPILOT_AGENT_APPROVAL", "annotate"));
            _systemPrompt = LoadSystemPrompt();
            _plannerSessionId = string.Empty;
        }

        public static async Task<string> TestDirectConnectionAsync(string provider, string model, string apiKey, string apiBaseUrl)
        {
            string serviceBaseUrl = Config.Get("CADCOPILOT_API_BASE_URL", "http://127.0.0.1:8000").Trim();
            ClaudeClient client = new ClaudeClient("standard", serviceBaseUrl, provider, apiKey, apiBaseUrl, model);
            return await client.TestConnectionAsync();
        }

        public async Task<DrawCommandResponse> GetDrawCommands(string userText, byte[] imageData)
        {
            if (UseBackendTransport())
            {
                LlmTextResponse serviceResponse = await CallBackendEndpoint(userText, imageData, "draw");
                return new DrawCommandResponse
                {
                    Commands = serviceResponse != null ? serviceResponse.Commands : null,
                    ReplyText = serviceResponse != null ? serviceResponse.ReplyText : null,
                    LegacyFallbackUsed = serviceResponse != null && serviceResponse.LegacyFallbackUsed,
                    PlannerSessionId = serviceResponse != null ? serviceResponse.PlannerSessionId : null,
                    TraceId = serviceResponse != null ? ResolveResponseTraceId(serviceResponse) : null,
                    ModelProvider = serviceResponse != null ? serviceResponse.ModelProvider : null,
                    ModelName = serviceResponse != null ? serviceResponse.ModelName : null,
                    PlannerState = serviceResponse != null ? serviceResponse.PlannerState : null,
                    TaskStatus = serviceResponse != null ? GetPlannerTaskStatus(serviceResponse) : null,
                    ExecutedTools = serviceResponse != null ? GetPlannerExecutedTools(serviceResponse) : null,
                    SelectedSkills = serviceResponse != null ? GetPlannerSelectedSkills(serviceResponse) : null,
                    ExecutionEvents = serviceResponse != null ? GetPlannerExecutionEvents(serviceResponse) : null,
                    PlannerCompletedSteps = serviceResponse != null ? GetPlannerCompletedSteps(serviceResponse) : null,
                    PlannerPendingSteps = serviceResponse != null ? GetPlannerPendingSteps(serviceResponse) : null,
                    AskUserType = serviceResponse != null ? GetPlannerAskUserType(serviceResponse) : null,
                    AskUserHint = serviceResponse != null ? GetPlannerAskUserHint(serviceResponse) : null
                };
            }

            string responseText = await CallDirectProvider(userText, imageData, true);
            string json = ExtractJson(responseText);
            if (string.IsNullOrWhiteSpace(json))
            {
                return new DrawCommandResponse
                {
                    Commands = null,
                    ReplyText = responseText
                };
            }

            DrawCommandResponse parsed = DeserializeDrawCommandResponse(json);
            if (parsed != null && string.IsNullOrWhiteSpace(parsed.ReplyText))
            {
                parsed.ReplyText = parsed.Explanation;
            }

            return parsed;
        }

        public async Task<string> Chat(string userText, byte[] imageData)
        {
            LlmTextResponse response = await ChatWithMetadata(userText, imageData);
            return response != null ? response.ReplyText : string.Empty;
        }

        public async Task<LlmTextResponse> ChatWithMetadata(string userText, byte[] imageData)
        {
            if (UseBackendTransport())
            {
                return await CallBackendEndpoint(userText, imageData, "chat");
            }

            return new LlmTextResponse
            {
                ReplyText = await CallDirectProvider(userText, imageData, false)
            };
        }

        public async Task<PlannerTaskDetailResponse> GetPlannerTaskDetailAsync(string taskId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim());
            return await GetBackendJsonAsync<PlannerTaskDetailResponse>(url);
        }

        public async Task<PlannerTaskEventsResponse> GetPlannerTaskEventsAsync(string taskId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/events";
            return await GetBackendJsonAsync<PlannerTaskEventsResponse>(url);
        }

        public async Task<List<PlannerTaskSummaryResponse>> ListRecentPlannerTasksAsync(int limit, string statusFilter = null)
        {
            if (!UseBackendTransport())
            {
                return new List<PlannerTaskSummaryResponse>();
            }

            int safeLimit = Math.Max(0, limit);
            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks?limit=" + safeLimit.ToString(CultureInfo.InvariantCulture);
            string normalizedStatus = (statusFilter ?? string.Empty).Trim();
            if (!string.IsNullOrWhiteSpace(normalizedStatus))
            {
                url += "&status=" + Uri.EscapeDataString(normalizedStatus);
            }
            List<PlannerTaskSummaryResponse> tasks = await GetBackendJsonAsync<List<PlannerTaskSummaryResponse>>(url);
            return tasks ?? new List<PlannerTaskSummaryResponse>();
        }

        public async Task<SkillDefinitionResponse> GetPlannerSkillAsync(string skillId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(skillId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/skills/" + Uri.EscapeDataString(skillId.Trim());
            return await GetBackendJsonAsync<SkillDefinitionResponse>(url);
        }

        public async Task<JObject> GetConnectorHealthAsync()
        {
            if (!UseBackendTransport())
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/health";
            return await GetBackendJsonAsync<JObject>(url);
        }

        public async Task<JObject> GetConnectorDiagnosticsAsync()
        {
            if (!UseBackendTransport())
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/connector/diagnostics";
            return await GetBackendJsonAsync<JObject>(url);
        }

        public string GetCurrentPlannerSessionId()
        {
            return _plannerSessionId ?? string.Empty;
        }

        public void SetCurrentPlannerSessionId(string plannerSessionId)
        {
            _plannerSessionId = (plannerSessionId ?? string.Empty).Trim();
        }

        public async Task<DrawCommandResponse> RetryPlannerTaskAsync(string taskId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/retry";
            string responseText = await PostBackendAsync(url, null);
            DrawCommandResponse parsed = DeserializeDrawCommandResponse(responseText);
            if (parsed != null)
            {
                UpdatePlannerSessionState(new LlmTextResponse
                {
                    PlannerSessionId = parsed.PlannerSessionId,
                    TraceId = parsed.TraceId,
                    PlannerState = parsed.PlannerState,
                    TaskStatus = parsed.TaskStatus
                }, "draw");
            }

            return parsed;
        }

        public async Task<DrawCommandResponse> ResumePlannerTaskAsync(string taskId, string message)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string resumeMessage = (message ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(resumeMessage))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/resume";
            string payload = JsonConvert.SerializeObject(new { message = resumeMessage });
            string responseText = await PostBackendAsync(url, payload);
            DrawCommandResponse parsed = DeserializeDrawCommandResponse(responseText);
            if (parsed != null)
            {
                UpdatePlannerSessionState(new LlmTextResponse
                {
                    PlannerSessionId = parsed.PlannerSessionId,
                    TraceId = parsed.TraceId,
                    PlannerState = parsed.PlannerState,
                    TaskStatus = parsed.TaskStatus
                }, "draw");
            }

            return parsed;
        }

        public async Task<PlannerTaskDetailResponse> CancelPlannerTaskAsync(string taskId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/cancel";
            string responseText = await PostBackendAsync(url, null);
            return JsonConvert.DeserializeObject<PlannerTaskDetailResponse>(responseText);
        }

        public async Task<SkillDraftResponse> CreateSkillDraftFromTaskAsync(string taskId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/skill-draft";
            string responseText = await PostBackendAsync(url, null);
            return JsonConvert.DeserializeObject<SkillDraftResponse>(responseText);
        }

        public async Task<PlannerTaskDetailResponse> RecordPlannerPermissionDecisionAsync(string taskId, string decision, string message, string traceId)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string normalizedDecision = string.IsNullOrWhiteSpace(decision) ? "deny" : decision.Trim();
            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/permission-decision";
            string payload = JsonConvert.SerializeObject(new
            {
                decision = normalizedDecision,
                message = message ?? string.Empty,
                trace_id = traceId ?? string.Empty
            });
            string responseText = await PostBackendAsync(url, payload);
            return JsonConvert.DeserializeObject<PlannerTaskDetailResponse>(responseText);
        }

        public async Task<PlannerTaskDetailResponse> RecordPlannerLocalResultAsync(string taskId, int affectedEntitiesCount, string traceId, string message, bool succeeded = true, JObject details = null)
        {
            if (!UseBackendTransport() || string.IsNullOrWhiteSpace(taskId))
            {
                return null;
            }

            string url = _serviceBaseUrl.TrimEnd('/') + "/planner/tasks/" + Uri.EscapeDataString(taskId.Trim()) + "/local-result";
            string payload = JsonConvert.SerializeObject(new
            {
                status = succeeded ? "completed" : "failed",
                message = string.IsNullOrWhiteSpace(message) ? (succeeded ? "Local CAD write completed." : "Local CAD write failed.") : message,
                affected_entities_count = Math.Max(0, affectedEntitiesCount),
                trace_id = traceId ?? string.Empty,
                tool_name = "local_apply_preview",
                details = details ?? new JObject()
            });
            string responseText = await PostBackendAsync(url, payload);
            return JsonConvert.DeserializeObject<PlannerTaskDetailResponse>(responseText);
        }

        public async Task<string> TestConnectionAsync()
        {
            string reply = await Chat("连接测试：请只回复 OK。", null);
            string preview = BuildReplyPreview(reply);
            if (UseBackendTransport())
            {
                string modeLabel = UseAgentMode() ? "智能体模式" : "标准模式";
                string backendProvider = ResolveBackendProvider();
                string backendModel = ResolveBackendModel(UseAgentMode() ? "draw" : "chat", backendProvider);
                if (string.IsNullOrWhiteSpace(backendModel))
                {
                    backendModel = "后台默认模型";
                }
                return modeLabel + "连接成功。后端地址: " + _serviceBaseUrl + "，当前模型: " + backendModel + "，返回: " + preview;
            }

            string provider = GetProviderDisplayName(_directProvider);
            string model = string.Equals(_directProvider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase) ? _claudeModel : _openAiModel;
            return provider + " 问答连接成功。当前模型: " + model + "，返回: " + preview;
        }

        private async Task<LlmTextResponse> CallBackendEndpoint(string userText, byte[] imageData, string mode)
        {
            string url = _serviceBaseUrl.TrimEnd('/') + "/chat/message";
            string backendProvider = ResolveBackendProvider();
            LlmRequest payload = new LlmRequest
            {
                Message = userText,
                Mode = mode,
                UserId = Config.Get("CADCOPILOT_CLIENT_ID", "cad-plugin"),
                ImageBase64 = imageData != null ? Convert.ToBase64String(imageData) : null,
                Model = ResolveBackendModel(mode, backendProvider),
                Provider = backendProvider,
                ApiKey = string.Equals(backendProvider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase) ? string.Empty : _openAiApiKey,
                ApiBaseUrl = string.Equals(backendProvider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase) ? string.Empty : _openAiApiBaseUrl,
                PlannerSessionId = string.Equals(mode, "draw", StringComparison.OrdinalIgnoreCase) ? _plannerSessionId : null,
                TraceId = Guid.NewGuid().ToString("N"),
                AgentApproval = string.Equals(mode, "draw", StringComparison.OrdinalIgnoreCase) ? _agentApproval : null
            };

            HttpResponseMessage response;
            string responseText;
            try
            {
                HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, url);
                request.Content = new StringContent(JsonConvert.SerializeObject(payload), Encoding.UTF8, "application/json");
                response = await HttpClient.SendAsync(request);
                responseText = await response.Content.ReadAsStringAsync();
            }
            catch (TaskCanceledException)
            {
                throw new InvalidOperationException("copilot_backend 连接超时，请检查本地服务是否启动。");
            }
            catch (HttpRequestException ex)
            {
                throw new InvalidOperationException("copilot_backend 连接失败，请检查本地服务是否启动。详情: " + ex.Message);
            }

            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(ExtractBridgeErrorDetail(responseText, response.StatusCode));
            }

            DrawCommandResponse parsed = DeserializeDrawCommandResponse(responseText);
            LlmTextResponse serviceResponse = parsed == null
                ? JsonConvert.DeserializeObject<LlmTextResponse>(responseText)
                : new LlmTextResponse
                {
                    ReplyText = parsed.ReplyText,
                    Commands = parsed.Commands,
                    LegacyFallbackUsed = parsed.LegacyFallbackUsed,
                    PlannerSessionId = parsed.PlannerSessionId,
                    TraceId = parsed.TraceId,
                    ModelProvider = parsed.ModelProvider,
                    ModelName = parsed.ModelName,
                    PlannerState = parsed.PlannerState,
                    TaskStatus = parsed.TaskStatus,
                    ExecutedTools = parsed.ExecutedTools,
                    SelectedSkills = parsed.SelectedSkills,
                    ExecutionEvents = parsed.ExecutionEvents,
                    PlannerCompletedSteps = parsed.PlannerCompletedSteps,
                    PlannerPendingSteps = parsed.PlannerPendingSteps,
                    AskUserType = parsed.AskUserType,
                    AskUserHint = parsed.AskUserHint
                };

            UpdatePlannerSessionState(serviceResponse, mode);

            return serviceResponse;
        }

        public void ResetPlannerSession()
        {
            _plannerSessionId = string.Empty;
        }

        private void UpdatePlannerSessionState(LlmTextResponse response, string mode)
        {
            if (!string.Equals(mode, "draw", StringComparison.OrdinalIgnoreCase) || response == null)
            {
                return;
            }

            if (!string.IsNullOrWhiteSpace(response.PlannerSessionId))
            {
                _plannerSessionId = response.PlannerSessionId;
            }

            string taskStatus = GetPlannerTaskStatus(response);
            if (string.Equals(taskStatus, "completed", StringComparison.OrdinalIgnoreCase)
                || string.Equals(taskStatus, "failed", StringComparison.OrdinalIgnoreCase)
                || string.Equals(taskStatus, "cancelled", StringComparison.OrdinalIgnoreCase))
            {
                _plannerSessionId = string.Empty;
            }
        }

        private static string ResolveResponseTraceId(LlmTextResponse response)
        {
            if (response == null)
            {
                return string.Empty;
            }

            if (!string.IsNullOrWhiteSpace(response.TraceId))
            {
                return response.TraceId;
            }

            return response.PlannerState != null ? response.PlannerState.TraceId : string.Empty;
        }

        private static string GetPlannerTaskStatus(LlmTextResponse response)
        {
            if (response == null)
            {
                return string.Empty;
            }

            if (response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.TaskStatus))
            {
                return response.PlannerState.TaskStatus;
            }

            return response.TaskStatus ?? string.Empty;
        }

        private static System.Collections.Generic.List<string> GetPlannerExecutedTools(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.ExecutedTools != null)
            {
                return response.PlannerState.ExecutedTools;
            }

            return response != null ? response.ExecutedTools : null;
        }

        private static System.Collections.Generic.List<string> GetPlannerSelectedSkills(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.SelectedSkills != null)
            {
                return response.PlannerState.SelectedSkills;
            }

            return response != null ? response.SelectedSkills : null;
        }

        private static System.Collections.Generic.List<PlannerExecutionEventResponse> GetPlannerExecutionEvents(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.ExecutionEvents != null)
            {
                return response.PlannerState.ExecutionEvents;
            }

            return response != null ? response.ExecutionEvents : null;
        }

        private static System.Collections.Generic.List<string> GetPlannerCompletedSteps(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.CompletedSteps != null)
            {
                return response.PlannerState.CompletedSteps;
            }

            return response != null ? response.PlannerCompletedSteps : null;
        }

        private static System.Collections.Generic.List<string> GetPlannerPendingSteps(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && response.PlannerState.PendingSteps != null)
            {
                return response.PlannerState.PendingSteps;
            }

            return response != null ? response.PlannerPendingSteps : null;
        }

        private static string GetPlannerAskUserType(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.AskUserType))
            {
                return response.PlannerState.AskUserType;
            }

            return response != null ? response.AskUserType : null;
        }

        private static string GetPlannerAskUserHint(LlmTextResponse response)
        {
            if (response != null && response.PlannerState != null && !string.IsNullOrWhiteSpace(response.PlannerState.AskUserHint))
            {
                return response.PlannerState.AskUserHint;
            }

            return response != null ? response.AskUserHint : null;
        }

        private bool HasBackendService()
        {
            return !string.IsNullOrWhiteSpace(_serviceBaseUrl);
        }

        private static string ExtractBridgeErrorDetail(string responseText, HttpStatusCode statusCode)
        {
            if (!string.IsNullOrWhiteSpace(responseText))
            {
                try
                {
                    JToken payload = JToken.Parse(responseText);
                    JToken detailToken = payload.SelectToken("detail") ?? payload.SelectToken("message");
                    if (detailToken != null && !string.IsNullOrWhiteSpace(detailToken.ToString()))
                    {
                        return detailToken.ToString();
                    }
                }
                catch
                {
                }
            }

            return "copilot_backend 请求失败，HTTP " + (int)statusCode + "。";
        }

        private static async Task<T> GetBackendJsonAsync<T>(string url)
        {
            string responseText = await SendBackendRequestAsync(HttpMethod.Get, url, null);
            return JsonConvert.DeserializeObject<T>(responseText);
        }

        private static async Task<string> PostBackendAsync(string url, string jsonBody)
        {
            return await SendBackendRequestAsync(HttpMethod.Post, url, jsonBody);
        }

        private static async Task<string> SendBackendRequestAsync(HttpMethod method, string url, string jsonBody)
        {
            HttpResponseMessage response;
            string responseText;
            try
            {
                HttpRequestMessage request = new HttpRequestMessage(method, url);
                if (jsonBody != null)
                {
                    request.Content = new StringContent(jsonBody, Encoding.UTF8, "application/json");
                }

                response = await HttpClient.SendAsync(request);
                responseText = await response.Content.ReadAsStringAsync();
            }
            catch (TaskCanceledException)
            {
                throw new InvalidOperationException("copilot_backend 连接超时，请检查本地服务是否启动。");
            }
            catch (HttpRequestException ex)
            {
                throw new InvalidOperationException("copilot_backend 连接失败，请检查本地服务是否启动。详情: " + ex.Message);
            }

            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(ExtractBridgeErrorDetail(responseText, response.StatusCode));
            }

            return responseText;
        }

        private bool UseAgentMode()
        {
            return string.Equals(_connectionMode, "service", StringComparison.OrdinalIgnoreCase);
        }

        private bool UseBackendTransport()
        {
            return HasBackendService();
        }

        private string ResolveBackendProvider()
        {
            if (string.Equals(_directProvider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase))
            {
                return ProviderCadCopilot;
            }

            return string.IsNullOrWhiteSpace(_openAiApiKey) ? ProviderCadCopilot : _directProvider;
        }

        private string ResolveBackendModel(string mode, string backendProvider)
        {
            if (string.Equals(backendProvider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase))
            {
                return string.Empty;
            }

            if (string.Equals(mode, "draw", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(_serviceModel))
            {
                return _serviceModel;
            }

            return _openAiModel;
        }

        private async Task<string> CallDirectProvider(string userText, byte[] imageData, bool drawMode)
        {
            if (IsOpenAiCompatibleProvider(_directProvider))
            {
                return await CallOpenAi(userText, imageData, drawMode);
            }

            return await CallClaude(userText, imageData, drawMode);
        }

        private static DrawCommandResponse DeserializeDrawCommandResponse(string responseText)
        {
            if (string.IsNullOrWhiteSpace(responseText))
            {
                return null;
            }

            JObject payload;
            try
            {
                payload = JObject.Parse(responseText);
            }
            catch (JsonReaderException)
            {
                return JsonConvert.DeserializeObject<DrawCommandResponse>(responseText);
            }

            JArray commands = payload["commands"] as JArray;
            if (commands != null)
            {
                foreach (JToken command in commands)
                {
                    NormalizeNullableNumber(command, "radius");
                    NormalizeNullableNumber(command, "startAngle");
                    NormalizeNullableNumber(command, "endAngle");
                    NormalizeNullableNumber(command, "height");
                    NormalizeNullableNumber(command, "rotation");
                    NormalizeNullableNumber(command, "scale");
                    NormalizeNullableNumber(command, "offset");
                    NormalizeNullableBoolean(command, "closed");
                }
            }

            return payload.ToObject<DrawCommandResponse>();
        }

        private static void NormalizeNullableNumber(JToken command, string propertyName)
        {
            JToken token = command[propertyName];
            if (token == null || token.Type == JTokenType.Null || token.Type == JTokenType.Float || token.Type == JTokenType.Integer)
            {
                return;
            }

            if (token.Type == JTokenType.String)
            {
                double value;
                if (double.TryParse(token.ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out value))
                {
                    command[propertyName] = value;
                    return;
                }
            }

            command[propertyName] = null;
        }

        private static void NormalizeNullableBoolean(JToken command, string propertyName)
        {
            JToken token = command[propertyName];
            if (token == null || token.Type == JTokenType.Null || token.Type == JTokenType.Boolean)
            {
                return;
            }

            if (token.Type == JTokenType.String)
            {
                bool value;
                if (bool.TryParse(token.ToString(), out value))
                {
                    command[propertyName] = value;
                    return;
                }
            }

            command[propertyName] = null;
        }

        private async Task<string> CallClaude(string userText, byte[] imageData, bool drawMode)
        {
            if (string.IsNullOrWhiteSpace(_claudeApiKey) || string.Equals(_claudeApiKey, "YOUR_API_KEY_HERE", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("未配置 CLAUDE_API_KEY，或请改为配置 CADCOPILOT_API_BASE_URL 走 SaaS 接口。");
            }

            JArray content = new JArray();
            if (imageData != null)
            {
                content.Add(new JObject
                {
                    ["type"] = "image",
                    ["source"] = new JObject
                    {
                        ["type"] = "base64",
                        ["media_type"] = DetectMediaType(imageData),
                        ["data"] = Convert.ToBase64String(imageData)
                    }
                });
            }

            content.Add(new JObject
            {
                ["type"] = "text",
                ["text"] = userText + (drawMode ? "\n\n如果用户要求绘图，请输出 JSON 指令。" : string.Empty)
            });

            JObject body = new JObject
            {
                ["model"] = _claudeModel,
                ["max_tokens"] = 4096,
                ["system"] = _systemPrompt,
                ["messages"] = new JArray
                {
                    new JObject
                    {
                        ["role"] = "user",
                        ["content"] = content
                    }
                }
            };

            string baseUrl = string.IsNullOrWhiteSpace(_openAiApiBaseUrl) ? "https://api.anthropic.com/v1" : _openAiApiBaseUrl.TrimEnd('/');
            HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/messages");
            if (!string.IsNullOrWhiteSpace(_claudeApiKey))
            {
                request.Headers.Add("x-api-key", _claudeApiKey);
            }
            request.Headers.Add("anthropic-version", "2023-06-01");
            request.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");

            HttpResponseMessage response = await HttpClient.SendAsync(request);
            string responseBody = await response.Content.ReadAsStringAsync();
            EnsureProviderSuccess(response, responseBody, _directProvider);

            JObject responseJson = JObject.Parse(responseBody);
            return responseJson["content"] != null && responseJson["content"][0] != null && responseJson["content"][0]["text"] != null
                ? responseJson["content"][0]["text"].ToString()
                : string.Empty;
        }

        private async Task<string> CallOpenAi(string userText, byte[] imageData, bool drawMode)
        {
            if (ProviderRequiresApiKey(_directProvider)
                && (string.IsNullOrWhiteSpace(_openAiApiKey) || string.Equals(_openAiApiKey, "YOUR_API_KEY_HERE", StringComparison.OrdinalIgnoreCase)))
            {
                throw new InvalidOperationException("未配置 OPENAI_API_KEY，请在设置中填写 API Key，或改为配置 CADCOPILOT_API_BASE_URL 走 SaaS 接口。");
            }

            JArray userContent = new JArray();
            userContent.Add(new JObject
            {
                ["type"] = "text",
                ["text"] = userText + (drawMode ? "\n\n如果用户要求绘图，请输出 JSON 指令。" : string.Empty)
            });

            if (imageData != null)
            {
                userContent.Add(new JObject
                {
                    ["type"] = "image_url",
                    ["image_url"] = new JObject
                    {
                        ["url"] = "data:" + DetectMediaType(imageData) + ";base64," + Convert.ToBase64String(imageData)
                    }
                });
            }

            JObject body = new JObject
            {
                ["model"] = _openAiModel,
                ["temperature"] = 0.2,
                ["messages"] = new JArray
                {
                    new JObject
                    {
                        ["role"] = "system",
                        ["content"] = _systemPrompt
                    },
                    new JObject
                    {
                        ["role"] = "user",
                        ["content"] = userContent
                    }
                }
            };

            string requestUrl = (_openAiApiBaseUrl.TrimEnd('/') + "/chat/completions").Trim();
            HttpRequestMessage request = new HttpRequestMessage(HttpMethod.Post, requestUrl);
            if (!string.IsNullOrWhiteSpace(_openAiApiKey))
            {
                request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _openAiApiKey);
            }
            request.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");

            try
            {
                HttpResponseMessage response = await HttpClient.SendAsync(request);
                string responseBody = await response.Content.ReadAsStringAsync();
                EnsureProviderSuccess(response, responseBody, _directProvider);

                JObject responseJson = JObject.Parse(responseBody);
                return ExtractOpenAiText(responseJson.SelectToken("choices[0].message.content"));
            }
            catch (TaskCanceledException)
            {
                throw new InvalidOperationException("连接超时，请检查网络、接口地址或当前模型服务状态。");
            }
            catch (HttpRequestException ex)
            {
                throw new InvalidOperationException("连接失败，请检查网络连接或接口地址。" + (string.IsNullOrWhiteSpace(ex.Message) ? string.Empty : " 详情: " + ex.Message));
            }
        }

        private static void EnsureProviderSuccess(HttpResponseMessage response, string responseBody, string provider)
        {
            if (response.IsSuccessStatusCode)
            {
                return;
            }

            string normalizedBody = (responseBody ?? string.Empty).ToLowerInvariant();
            string providerName = GetProviderDisplayName(provider);
            string apiMessage = ExtractApiErrorMessage(responseBody);

            if (response.StatusCode == HttpStatusCode.Unauthorized || response.StatusCode == HttpStatusCode.Forbidden
                || normalizedBody.Contains("incorrect api key")
                || normalizedBody.Contains("invalid api key")
                || normalizedBody.Contains("authentication")
                || normalizedBody.Contains("unauthorized"))
            {
                throw new InvalidOperationException(providerName + " API Key 不正确，或当前 Key 没有访问权限。");
            }

            if (response.StatusCode == (HttpStatusCode)429
                || normalizedBody.Contains("insufficient_quota")
                || normalizedBody.Contains("quota")
                || normalizedBody.Contains("balance")
                || normalizedBody.Contains("credit")
                || normalizedBody.Contains("billing")
                || normalizedBody.Contains("余额不足")
                || normalizedBody.Contains("额度"))
            {
                throw new InvalidOperationException(providerName + " 账户余额不足、额度已用尽，或请求频率受限。");
            }

            if (response.StatusCode == HttpStatusCode.NotFound
                || normalizedBody.Contains("model_not_found")
                || normalizedBody.Contains("does not exist")
                || normalizedBody.Contains("not found"))
            {
                throw new InvalidOperationException(providerName + " 模型不可用，或模型名称不正确。");
            }

            throw new InvalidOperationException(string.IsNullOrWhiteSpace(apiMessage)
                ? providerName + " 连接失败，HTTP " + (int)response.StatusCode + "。"
                : providerName + " 连接失败: " + apiMessage);
        }

        private static string ExtractApiErrorMessage(string responseBody)
        {
            if (string.IsNullOrWhiteSpace(responseBody))
            {
                return string.Empty;
            }

            try
            {
                JToken payload = JToken.Parse(responseBody);
                JToken messageToken = payload.SelectToken("error.message") ?? payload.SelectToken("message");
                return messageToken != null ? messageToken.ToString().Trim() : string.Empty;
            }
            catch
            {
                return responseBody.Trim();
            }
        }

        private static string ExtractOpenAiText(JToken contentToken)
        {
            if (contentToken == null)
            {
                return string.Empty;
            }

            if (contentToken.Type == JTokenType.String)
            {
                return contentToken.ToString();
            }

            if (contentToken.Type != JTokenType.Array)
            {
                return contentToken.ToString();
            }

            StringBuilder builder = new StringBuilder();
            JArray items = (JArray)contentToken;
            for (int i = 0; i < items.Count; i++)
            {
                JToken item = items[i];
                string text = item["text"] != null
                    ? item["text"].ToString()
                    : item["content"] != null
                        ? item["content"].ToString()
                        : string.Empty;

                if (string.IsNullOrWhiteSpace(text))
                {
                    continue;
                }

                if (builder.Length > 0)
                {
                    builder.AppendLine();
                }

                builder.Append(text.Trim());
            }

            return builder.ToString();
        }

        private static string NormalizeProvider(string provider)
        {
            if (string.IsNullOrWhiteSpace(provider))
            {
                return ProviderMiniMax;
            }

            string normalized = provider.Trim().ToLowerInvariant();
            if (normalized == ProviderCadCopilot || normalized == "official" || normalized == "cad-copilot" || normalized == "cad_copilot")
            {
                return ProviderCadCopilot;
            }

            if (normalized == "openai" || normalized == "gpt" || normalized == "gpt-5" || normalized == "gpt-5.5")
            {
                return ProviderOpenAi;
            }

            if (normalized == ProviderDeepSeek)
            {
                return ProviderDeepSeek;
            }

            if (normalized == ProviderAnthropic || normalized == "claude")
            {
                return ProviderAnthropic;
            }

            if (normalized == ProviderMiniMax)
            {
                return ProviderMiniMax;
            }

            if (normalized == ProviderOpenAiCompatible || normalized == "openai-compatible" || normalized == "compatible")
            {
                return ProviderOpenAiCompatible;
            }

            if (normalized == ProviderOllama || normalized == "local")
            {
                return ProviderOllama;
            }

            if (normalized == ProviderEnterprisePrivate || normalized == "enterprise-private")
            {
                return ProviderEnterprisePrivate;
            }

            return ProviderOpenAiCompatible;
        }

        private static bool IsOpenAiCompatibleProvider(string provider)
        {
            return string.Equals(provider, ProviderOpenAi, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderMiniMax, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderOpenAiCompatible, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(provider, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase);
        }

        private static bool ProviderRequiresApiKey(string provider)
        {
            return !string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase)
                   && !string.Equals(provider, ProviderOpenAiCompatible, StringComparison.OrdinalIgnoreCase)
                   && !string.Equals(provider, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase);
        }

        private static string GetDefaultProviderBaseUrl(string provider)
        {
            if (string.Equals(provider, ProviderOpenAi, StringComparison.OrdinalIgnoreCase))
            {
                return "https://api.openai.com/v1";
            }
            if (string.Equals(provider, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase))
            {
                return "https://api.deepseek.com/v1";
            }
            if (string.Equals(provider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase))
            {
                return "https://api.anthropic.com/v1";
            }
            if (string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase))
            {
                return "http://127.0.0.1:11434/v1";
            }
            return string.Equals(provider, ProviderMiniMax, StringComparison.OrdinalIgnoreCase)
                ? "https://api.minimaxi.com/v1"
                : string.Empty;
        }

        private static string GetDefaultProviderModel(string provider)
        {
            if (string.Equals(provider, ProviderOpenAi, StringComparison.OrdinalIgnoreCase))
            {
                return "gpt-5.5";
            }
            if (string.Equals(provider, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase))
            {
                return "deepseek-v4";
            }
            if (string.Equals(provider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase))
            {
                return "claude-sonnet-4-20250514";
            }
            if (string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase))
            {
                return "qwen3:8b";
            }
            if (string.Equals(provider, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase))
            {
                return "enterprise-default";
            }
            if (string.Equals(provider, ProviderOpenAiCompatible, StringComparison.OrdinalIgnoreCase))
            {
                return "model-name";
            }
            return "MiniMax-M2.7";
        }

        private static string GetProviderDisplayName(string provider)
        {
            if (string.Equals(provider, ProviderCadCopilot, StringComparison.OrdinalIgnoreCase))
            {
                return "AgentBridge";
            }

            if (string.Equals(provider, ProviderOpenAi, StringComparison.OrdinalIgnoreCase))
            {
                return "OpenAI";
            }

            if (string.Equals(provider, ProviderDeepSeek, StringComparison.OrdinalIgnoreCase))
            {
                return "DeepSeek";
            }

            if (string.Equals(provider, ProviderMiniMax, StringComparison.OrdinalIgnoreCase))
            {
                return "MiniMax";
            }

            if (string.Equals(provider, ProviderAnthropic, StringComparison.OrdinalIgnoreCase))
            {
                return "Anthropic / Claude";
            }

            if (string.Equals(provider, ProviderOllama, StringComparison.OrdinalIgnoreCase))
            {
                return "Ollama";
            }

            if (string.Equals(provider, ProviderEnterprisePrivate, StringComparison.OrdinalIgnoreCase))
            {
                return "企业内网模型";
            }

            return "OpenAI Compatible";
        }

        private static string NormalizeAgentApproval(string value)
        {
            string normalized = (value ?? string.Empty).Trim().ToLowerInvariant();
            if (normalized == "execute" || normalized == "run_for_me")
            {
                return "execute";
            }

            if (normalized == "full" || normalized == "full_approval")
            {
                return "full";
            }

            return "annotate";
        }

        private static string NormalizeConnectionMode(string mode, string serviceBaseUrl)
        {
            if (!string.IsNullOrWhiteSpace(mode))
            {
                string normalized = mode.Trim().ToLowerInvariant();
                if (normalized == "standard" || normalized == "direct")
                {
                    return "standard";
                }

                if (normalized == "service")
                {
                    return "service";
                }

                if (normalized == "plan")
                {
                    return "standard";
                }
            }

            return string.IsNullOrWhiteSpace(serviceBaseUrl) ? "standard" : "service";
        }

        private static string BuildReplyPreview(string reply)
        {
            string normalized = (reply ?? string.Empty).Trim();
            if (normalized.Length == 0)
            {
                return "空响应";
            }

            normalized = normalized.Replace("\r", " ").Replace("\n", " ");
            return normalized.Length <= 60 ? normalized : normalized.Substring(0, 60) + "...";
        }

        private static string ExtractJson(string response)
        {
            int jsonStart = response.IndexOf("```json", StringComparison.OrdinalIgnoreCase);
            if (jsonStart >= 0)
            {
                jsonStart = response.IndexOf('\n', jsonStart);
                if (jsonStart >= 0)
                {
                    int jsonEnd = response.IndexOf("```", jsonStart + 1, StringComparison.OrdinalIgnoreCase);
                    if (jsonEnd > jsonStart)
                    {
                        return response.Substring(jsonStart + 1, jsonEnd - jsonStart - 1).Trim();
                    }
                }
            }

            int braceStart = response.IndexOf('{');
            int braceEnd = response.LastIndexOf('}');
            if (braceStart >= 0 && braceEnd > braceStart)
            {
                string candidate = response.Substring(braceStart, braceEnd - braceStart + 1);
                if (candidate.Contains("\"commands\""))
                {
                    return candidate;
                }
            }

            return null;
        }

        private static string DetectMediaType(byte[] data)
        {
            if (data.Length > 3 && data[0] == 0x89 && data[1] == 0x50)
            {
                return "image/png";
            }

            if (data.Length > 2 && data[0] == 0xFF && data[1] == 0xD8)
            {
                return "image/jpeg";
            }

            return "image/png";
        }

        private static string LoadSystemPrompt()
        {
            string filePath = Path.Combine(Path.GetDirectoryName(typeof(ClaudeClient).Assembly.Location) ?? AppDomain.CurrentDomain.BaseDirectory, "Resources", "system_prompt.txt");
            if (File.Exists(filePath))
            {
                return File.ReadAllText(filePath);
            }

            return "你是一个专业的 AutoCAD 绘图助手。优先输出 JSON 绘图指令，格式包含 commands 数组。";
        }
    }
}
