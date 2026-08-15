using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using AgentBridge.Core;
using AgentBridge.UI;
using System.Net;

[assembly: ExtensionApplication(typeof(AgentBridge.Plugin.CadCopilotApp))]
[assembly: CommandClass(typeof(AgentBridge.Plugin.Commands))]

namespace AgentBridge.Plugin
{
    public class CadCopilotApp : IExtensionApplication
    {
        public void Initialize()
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            Application.Idle += OnFirstIdle;
            Logger.Info("AgentBridge loaded. Use AICHAT to open the panel.");
        }

        public void Terminate()
        {
            Application.Idle -= OnFirstIdle;
            LocalToolBridge.Stop();
            DrawingContextService.Shutdown();
            MainThreadDispatcher.Shutdown();
            CopilotPalette.Dispose();
            Logger.Info("AgentBridge unloaded.");
        }

        private void OnFirstIdle(object sender, System.EventArgs e)
        {
            Application.Idle -= OnFirstIdle;
            Config.Load();
            MainThreadDispatcher.Initialize();
            DrawingContextService.Initialize();
            // 本地桥改为惰性启动（TESTCOPILOT / AICHAT 首次使用时拉起），
            // 避免 AutoCAD 启动阶段创建监听线程（在资源紧张的机器上曾触发 R6016）。
            Logger.Info("AgentBridge initialization completed (bridge starts lazily on first command).");
        }
    }
}