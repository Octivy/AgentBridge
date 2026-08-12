using System;
using System.Globalization;
using AgentBridge.LLM;
using Newtonsoft.Json.Linq;

namespace AgentBridge.UI
{
    public sealed class HarnessEventDisplayModel
    {
        public string Title { get; set; } = "事件";
        public string Summary { get; set; } = string.Empty;
        public string Detail { get; set; } = string.Empty;
        public string Tone { get; set; } = "muted";
        public string Marker { get; set; } = "•";
        public bool CollapseDefault { get; set; }
    }

    public static class HarnessEventDisplayFormatter
    {
        public static HarnessEventDisplayModel Format(HarnessEventResponse item)
        {
            if (item == null)
            {
                return new HarnessEventDisplayModel();
            }

            string eventType = (item.EventType ?? string.Empty).Trim().ToLowerInvariant();
            HarnessEventDisplayModel model = new HarnessEventDisplayModel
            {
                Title = ResolveTitle(eventType),
                Tone = ResolveTone(eventType),
                Marker = ResolveMarker(eventType),
                CollapseDefault = item.CollapseDefault
            };
            model.Summary = ResolveSummary(item, eventType);
            model.Detail = ResolveDetail(item, eventType);
            return model;
        }

        private static string ResolveTitle(string eventType)
        {
            switch (eventType)
            {
                case "plan_created":
                    return "已生成计划";
                case "plan_revised":
                    return "已更新计划";
                case "tool_requested":
                    return "准备调用工具";
                case "tool_started":
                    return "正在运行工具";
                case "tool_result":
                    return "工具结果";
                case "dry_run_preview_created":
                    return "已生成预览";
                case "permission_requested":
                    return "等待批准";
                case "cad_transaction_started":
                    return "开始写入事务";
                case "cad_write_applied":
                    return "已写入图纸";
                case "task_completed":
                    return "任务完成";
                case "task_failed":
                    return "任务失败";
                default:
                    return string.IsNullOrWhiteSpace(eventType) ? "事件" : eventType.Replace("_", " ");
            }
        }

        private static string ResolveTone(string eventType)
        {
            if (eventType.Contains("failed") || eventType.Contains("error"))
            {
                return "danger";
            }
            if (eventType.Contains("permission") || eventType.Contains("preview"))
            {
                return "warning";
            }
            if (eventType.Contains("result") || eventType.Contains("completed") || eventType.Contains("applied"))
            {
                return "success";
            }
            return "muted";
        }

        private static string ResolveMarker(string eventType)
        {
            if (eventType.Contains("failed"))
            {
                return "x";
            }
            if (eventType.Contains("permission"))
            {
                return "!";
            }
            if (eventType.Contains("preview"))
            {
                return "o";
            }
            if (eventType.Contains("result") || eventType.Contains("completed") || eventType.Contains("applied"))
            {
                return "✓";
            }
            return "•";
        }

        private static string ResolveSummary(HarnessEventResponse item, string eventType)
        {
            string summary = (item.Summary ?? string.Empty).Trim();
            if (!string.IsNullOrWhiteSpace(summary))
            {
                return summary;
            }

            JObject payload = item.Payload;
            if (payload == null)
            {
                return string.Empty;
            }

            if (eventType == "cad_write_applied")
            {
                int? count = ReadInt(payload.SelectToken("affected_entities_count"));
                if (count.HasValue)
                {
                    return "影响 " + count.Value.ToString(CultureInfo.InvariantCulture) + " 个图元";
                }
            }

            JToken resultSummary = payload.SelectToken("result.summary");
            if (resultSummary != null && resultSummary.Type != JTokenType.Null)
            {
                return resultSummary.ToString();
            }

            JToken pendingSteps = payload.SelectToken("pending_steps");
            if (pendingSteps is JArray steps && steps.Count > 0)
            {
                return steps.Count.ToString(CultureInfo.InvariantCulture) + " 个步骤";
            }

            return string.Empty;
        }

        private static string ResolveDetail(HarnessEventResponse item, string eventType)
        {
            JObject payload = item.Payload;
            if (payload == null)
            {
                return string.Empty;
            }

            if (eventType == "cad_write_applied" || eventType == "cad_transaction_started")
            {
                return payload.SelectToken("transaction.transaction_id")?.ToString() ?? string.Empty;
            }

            JToken toolName = payload.SelectToken("tool_name") ?? payload.SelectToken("tool_calls[0]");
            return toolName != null && toolName.Type != JTokenType.Null ? toolName.ToString() : string.Empty;
        }

        private static int? ReadInt(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null)
            {
                return null;
            }
            if (token.Type == JTokenType.Integer)
            {
                return token.Value<int>();
            }
            if (int.TryParse(token.ToString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out int value))
            {
                return value;
            }
            return null;
        }
    }
}
