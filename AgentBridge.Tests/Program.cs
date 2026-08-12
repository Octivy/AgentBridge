using System;
using System.IO;

namespace AgentBridge.Tests
{
    internal static class Program
    {
        private static int _failed;

        private static int Main()
        {
            string root = FindRepositoryRoot();
            Run("plugin exposes minimal AutoCAD commands", () => PluginCommandsAreMinimal(root));
            Run("local bridge exposes product writes", () => LocalBridgeUsesProductContract(root));
            Run("command executor supports verified rollback", () => CommandExecutorSupportsRollback(root));
            Run("chat panel has no architecture toolbar dependency", () => ChatPanelHasNoLegacyToolbar(root));
            Run("connector exposes supported model families", () => ConnectorSupportsModelFamilies(root));
            Run("plugin has no commercial platform dependency", () => PluginHasNoCommercialPlatformDependency(root));
            Console.WriteLine(_failed == 0 ? "All contract tests passed." : _failed + " contract test(s) failed.");
            return _failed == 0 ? 0 : 1;
        }

        private static void PluginCommandsAreMinimal(string root)
        {
            string source = File.ReadAllText(Path.Combine(root, "Plugin", "Commands.cs"));
            Require(source, "[CommandMethod(\"AICHAT\"");
            Require(source, "[CommandMethod(\"AISNAPSHOT\"");
            Reject(source, "AITOOLBAR");
            Reject(source, "AIWALL");
            Reject(source, "AIDRAW");
            Reject(source, "AgentBridge.Architecture");
        }

        private static void LocalBridgeUsesProductContract(string root)
        {
            string source = File.ReadAllText(Path.Combine(root, "Core", "LocalToolBridge.cs"));
            Require(source, "arch_draw_outer_outline");
            Require(source, "arch_apply_layer_mapping");
            Require(source, "cad_rollback_transaction");
            Require(source, "ExecuteAtomic");
            Reject(source, "arch_create_wall");
            Reject(source, "arch_place_opening");
        }

        private static void CommandExecutorSupportsRollback(string root)
        {
            string source = File.ReadAllText(Path.Combine(root, "Engine", "CommandExecutor.cs"));
            Require(source, "ExecuteAtomic");
            Require(source, "RegisterMutationRollback");
            Require(source, "DescribeRollback");
            Require(source, "RollbackAtomic");
        }

        private static void ChatPanelHasNoLegacyToolbar(string root)
        {
            string xaml = File.ReadAllText(Path.Combine(root, "UI", "ChatPanel.xaml"));
            string code = File.ReadAllText(Path.Combine(root, "UI", "ChatPanel.xaml.cs"));
            Reject(xaml, "ArchitectureToolbarButton_Click");
            Reject(code, "ArchitectureToolbarPalette");
            Require(xaml, "专业技能");
            Require(code, "recognize_drawing");
            Require(code, "recognize_functional_objects");
            Require(code, "outer_outline");
            Require(code, "layer_standard");
            if (CountOccurrences(code, "new ToolDefinition(") != 4)
            {
                throw new InvalidOperationException("Chat panel must expose exactly four current Skill shortcuts.");
            }
        }

        private static void PluginHasNoCommercialPlatformDependency(string root)
        {
            string xaml = File.ReadAllText(Path.Combine(root, "UI", "ChatPanel.xaml"));
            string code = File.ReadAllText(Path.Combine(root, "UI", "ChatPanel.xaml.cs"));
            string client = File.ReadAllText(Path.Combine(root, "LLM", "ClaudeClient.cs"));
            string models = File.ReadAllText(Path.Combine(root, "LLM", "LlmMessage.cs"));
            Reject(xaml, "AccountLogin_Click");
            Reject(xaml, "FooterUsageButton");
            Reject(xaml, "OpenUpdateFromSettings_Click");
            Reject(xaml, "Tag=\"plan\"");
            Reject(code, "StartWebLoginAsync");
            Reject(code, "CADCOPILOT_AUTH_TOKEN");
            Reject(client, "/auth/");
            Reject(client, "/product/");
            Reject(client, "/plugin/update/");
            Reject(models, "ProductCredit");
            Reject(models, "ProductPlan");
        }

        private static void ConnectorSupportsModelFamilies(string root)
        {
            string xaml = File.ReadAllText(Path.Combine(root, "UI", "ChatPanel.xaml"));
            string code = File.ReadAllText(Path.Combine(root, "LLM", "ClaudeClient.cs"));
            string bridge = File.ReadAllText(Path.Combine(root, "Core", "LocalToolBridge.cs"));
            Require(xaml, "Tag=\"anthropic\"");
            Require(xaml, "Tag=\"openai_compatible\"");
            Require(xaml, "Tag=\"ollama\"");
            Require(xaml, "Tag=\"enterprise_private\"");
            Require(code, "GetConnectorDiagnosticsAsync");
            Require(code, "/planner/tasks/");
            Require(code, "/skill-draft");
            Require(bridge, "private const string ProtocolVersion = \"2.0\"");
            Require(bridge, "protocol_version = ProtocolVersion");
        }

        private static int CountOccurrences(string value, string marker)
        {
            int count = 0;
            int offset = 0;
            while ((offset = value.IndexOf(marker, offset, StringComparison.Ordinal)) >= 0)
            {
                count++;
                offset += marker.Length;
            }
            return count;
        }

        private static string FindRepositoryRoot()
        {
            DirectoryInfo current = new DirectoryInfo(AppContext.BaseDirectory);
            while (current != null)
            {
                if (File.Exists(Path.Combine(current.FullName, "AgentBridge.csproj")))
                {
                    return current.FullName;
                }
                current = current.Parent;
            }
            throw new DirectoryNotFoundException("AgentBridge repository root not found.");
        }

        private static void Require(string value, string expected)
        {
            if (value.IndexOf(expected, StringComparison.Ordinal) < 0)
            {
                throw new InvalidOperationException("Expected contract marker: " + expected);
            }
        }

        private static void Reject(string value, string unexpected)
        {
            if (value.IndexOf(unexpected, StringComparison.Ordinal) >= 0)
            {
                throw new InvalidOperationException("Legacy contract marker remains: " + unexpected);
            }
        }

        private static void Run(string name, Action test)
        {
            try
            {
                test();
                Console.WriteLine("PASS " + name);
            }
            catch (Exception ex)
            {
                _failed++;
                Console.WriteLine("FAIL " + name + ": " + ex.Message);
            }
        }
    }
}
