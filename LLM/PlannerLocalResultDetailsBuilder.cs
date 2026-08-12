using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;

namespace AgentBridge.LLM
{
    public static class PlannerLocalResultDetailsBuilder
    {
        public static JObject Build(string taskId, IEnumerable<DrawCommand> commands, int affectedEntitiesCount)
        {
            string normalizedTaskId = (taskId ?? string.Empty).Trim();
            string transactionId = "cadtx_" + Guid.NewGuid().ToString("N");
            string undoGroup = string.IsNullOrWhiteSpace(normalizedTaskId)
                ? "CADCOPILOT_" + transactionId
                : "CADCOPILOT_TASK_" + normalizedTaskId;

            JArray affectedEntities = new JArray();
            if (commands != null)
            {
                foreach (DrawCommand command in commands)
                {
                    if (command == null)
                    {
                        continue;
                    }

                    affectedEntities.Add(new JObject
                    {
                        ["entity_id"] = string.Empty,
                        ["operation"] = "created",
                        ["type"] = NormalizeEntityType(command.Type),
                        ["layer"] = command.Layer ?? string.Empty
                    });
                }
            }

            int safeCount = Math.Max(0, affectedEntitiesCount);
            if (safeCount == 0 && affectedEntities.Count > 0)
            {
                safeCount = affectedEntities.Count;
            }

            return new JObject
            {
                ["dry_run"] = false,
                ["affected_entities_count"] = safeCount,
                ["affected_entities"] = affectedEntities,
                ["transaction"] = new JObject
                {
                    ["transaction_id"] = transactionId,
                    ["undo_group"] = undoGroup,
                    ["rollback_token"] = transactionId,
                    ["rollback_supported"] = true
                }
            };
        }

        private static string NormalizeEntityType(string commandType)
        {
            string normalized = (commandType ?? string.Empty).Trim();
            return normalized.Length == 0
                ? "unknown"
                : normalized.ToLower(CultureInfo.InvariantCulture);
        }
    }
}
