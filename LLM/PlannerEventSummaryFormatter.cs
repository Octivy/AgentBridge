using System;
using Newtonsoft.Json.Linq;

namespace AgentBridge.LLM
{
    public static class PlannerEventSummaryFormatter
    {
        public static string GetDisplaySummary(PlannerExecutionEventResponse executionEvent)
        {
            if (executionEvent == null)
            {
                return string.Empty;
            }

            string semanticSummary = GetSemanticSummary(executionEvent);
            if (!string.IsNullOrWhiteSpace(semanticSummary))
            {
                return semanticSummary;
            }

            return NormalizePreviewSummary(executionEvent.Summary);
        }

        public static string GetSemanticSummary(PlannerExecutionEventResponse executionEvent)
        {
            JObject details = executionEvent != null ? executionEvent.Details : null;
            if (details == null)
            {
                return string.Empty;
            }

            string semanticSummary = ReadText(details, "semantic_summary");
            if (string.IsNullOrWhiteSpace(semanticSummary) || IsTechnicalDryRunText(semanticSummary))
            {
                return string.Empty;
            }

            return semanticSummary.Trim();
        }

        public static string NormalizePreviewSummary(string summary)
        {
            string value = (summary ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            if (IsTechnicalDryRunText(value))
            {
                return "已生成更改预览，等待你确认后应用到当前图纸。";
            }

            return value.Replace("dry_run", "写入前预览");
        }

        public static bool IsTechnicalDryRunText(string value)
        {
            string normalized = (value ?? string.Empty).Trim();
            if (normalized.Length == 0)
            {
                return false;
            }

            string lower = normalized.ToLowerInvariant();
            return lower.Contains("dry run")
                || lower.Contains("dry_run")
                || lower.Contains("real cad write")
                || lower.Contains("real write")
                || lower.Contains("local autocad plugin")
                || lower.Contains("nas")
                || lower.Contains("reply \"确认执行\"")
                || normalized.Contains("真实写入")
                || normalized.Contains("本地 AutoCAD 写入")
                || normalized.Contains("本地 AutoCAD 插件");
        }

        private static string ReadText(JObject details, string key)
        {
            JToken token = GetToken(details, key);
            return token != null ? (token.ToString() ?? string.Empty).Trim() : string.Empty;
        }

        private static JToken GetToken(JObject details, string key)
        {
            if (details == null || string.IsNullOrWhiteSpace(key))
            {
                return null;
            }

            JToken token;
            if (details.TryGetValue(key, StringComparison.OrdinalIgnoreCase, out token))
            {
                return token;
            }

            JObject data = details["data"] as JObject;
            if (data != null && data.TryGetValue(key, StringComparison.OrdinalIgnoreCase, out token))
            {
                return token;
            }

            return null;
        }
    }
}
