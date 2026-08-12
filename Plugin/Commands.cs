using System;
using System.Globalization;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using AgentBridge.Core;
using AgentBridge.Engine;
using AgentBridge.UI;

namespace AgentBridge.Plugin
{
    /// <summary>AutoCAD 2024 entry points; product actions are exposed by MCP tools.</summary>
    public class Commands
    {
        [CommandMethod("TestCopilot", CommandFlags.Modal)]
        public void TestCopilot()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document != null)
            {
                document.Editor.WriteMessage("\n[AgentBridge] Plugin and local MCP bridge are loaded.");
            }
        }

        [CommandMethod("AICHAT", CommandFlags.Modal)]
        public void OpenChat()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            try
            {
                CopilotPalette.Show();
            }
            catch (System.Exception ex)
            {
                Logger.Error("Failed to open AICHAT palette: " + ex);
                if (document != null)
                {
                    document.Editor.WriteMessage("\n[AgentBridge] AICHAT failed: " + ex.Message);
                }
                Application.ShowAlertDialog("AICHAT failed.\n\n" + ex.Message);
            }
        }

        [CommandMethod("AISNAPSHOT", CommandFlags.Modal)]
        public void TakeSnapshot()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            if (document == null)
            {
                return;
            }

            try
            {
                SnapshotResult snapshot = new SnapshotExtractor().ExtractL2Summary();
                string directory = Path.Combine(Path.GetTempPath(), "AgentBridge", "snapshots");
                Directory.CreateDirectory(directory);
                string drawingName = Path.GetFileNameWithoutExtension(document.Name) ?? "drawing";
                foreach (char invalid in Path.GetInvalidFileNameChars())
                {
                    drawingName = drawingName.Replace(invalid, '_');
                }
                string fileName = drawingName + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".json";
                string path = Path.Combine(directory, fileName);
                File.WriteAllText(path, snapshot.ToJson());
                document.Editor.WriteMessage(
                    "\n[AgentBridge] Snapshot exported: layers=" + snapshot.LayerCount
                    + ", entities=" + snapshot.EntityCount
                    + ", bytes=" + snapshot.JsonSize + "\n" + path);
                Logger.Info("Snapshot exported to " + path);
            }
            catch (System.Exception ex)
            {
                Logger.Error("AISNAPSHOT failed: " + ex);
                document.Editor.WriteMessage("\n[AgentBridge] AISNAPSHOT failed: " + ex.Message);
            }
        }
    }
}
