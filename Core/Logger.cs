using System;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices;

namespace AgentBridge.Core
{
    public static class Logger
    {
        private static readonly object LockObject = new object();
        private static readonly string LogPath;
        private const long MaxLogBytes = 5 * 1024 * 1024;

        static Logger()
        {
            string dllDir = Path.GetDirectoryName(typeof(Logger).Assembly.Location);
            LogPath = Path.Combine(dllDir ?? AppDomain.CurrentDomain.BaseDirectory, "cadcopilot.log");
        }

        public static void Info(string message)
        {
            Log("INFO", message);
        }

        public static void Warn(string message)
        {
            Log("WARN", message);
        }

        public static void Error(string message)
        {
            Log("ERROR", message);
        }

        private static void Log(string level, string message)
        {
            string line = "[" + DateTime.Now.ToString("HH:mm:ss") + "] [" + level + "] " + message;

            lock (LockObject)
            {
                try
                {
                    RotateIfNeeded();
                    File.AppendAllText(LogPath, line + Environment.NewLine);
                }
                catch (Exception ex)
                {
                    TryWriteFallback("Failed to write log file: " + ex.Message);
                }
            }

            if (level == "ERROR")
            {
                try
                {
                    Document document = Application.DocumentManager != null ? Application.DocumentManager.MdiActiveDocument : null;
                    if (document != null)
                    {
                        document.Editor.WriteMessage("\n[CadCopilot ERROR] " + message);
                    }
                }
                catch
                {
                    TryWriteFallback("Failed to write AutoCAD editor message.");
                }
            }
        }

        private static void RotateIfNeeded()
        {
            FileInfo file = new FileInfo(LogPath);
            if (!file.Exists || file.Length < MaxLogBytes)
            {
                return;
            }

            string backupPath = LogPath + ".1";
            if (File.Exists(backupPath))
            {
                File.Delete(backupPath);
            }

            File.Move(LogPath, backupPath);
        }

        private static void TryWriteFallback(string message)
        {
            try
            {
                Console.Error.WriteLine("[CadCopilot Logger] " + message);
            }
            catch
            {
                // Last-resort fallback; avoid throwing from logging.
            }
        }
    }
}
