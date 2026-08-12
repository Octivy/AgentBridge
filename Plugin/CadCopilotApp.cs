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
            LocalToolBridge.Start();
            Logger.Info("AgentBridge initialization completed.");
        }
    }
}