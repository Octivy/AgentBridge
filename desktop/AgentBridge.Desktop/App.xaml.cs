using System.IO;

namespace AgentBridge.Desktop;

public partial class App : System.Windows.Application
{
    public App()
    {
        DispatcherUnhandledException += (_, args) =>
        {
            Log("dispatcher unhandled: " + args.Exception);
            args.Handled = true;
        };
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
        {
            Log("appdomain unhandled: " + args.ExceptionObject);
        };
    }

    private static void Log(string message)
    {
        try
        {
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var stateDir = Path.Combine(appData, "AgentBridge");
            Directory.CreateDirectory(stateDir);
            File.AppendAllText(Path.Combine(stateDir, "desktop.log"), $"{DateTime.Now:O} {message}{Environment.NewLine}");
        }
        catch
        {
            // logging must never crash the app
        }
    }
}
