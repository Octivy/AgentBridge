using System.IO;
using System.Threading;
using System.Windows;

namespace AgentBridge.Desktop;

public partial class App : System.Windows.Application
{
    private static Mutex? _singleInstance;

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

    protected override void OnStartup(StartupEventArgs e)
    {
        // 单实例：开机自启与手动双击只保留第一个进程，避免重复拉起后端。
        _singleInstance = new Mutex(true, @"Local\AgentBridge.Desktop.SingleInstance", out bool createdNew);
        if (!createdNew)
        {
            Log("another instance is already running; this one exits");
            _singleInstance.Dispose();
            _singleInstance = null;
            Shutdown();
            return;
        }
        base.OnStartup(e);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try
        {
            _singleInstance?.ReleaseMutex();
            _singleInstance?.Dispose();
        }
        catch
        {
            // best-effort cleanup
        }
        base.OnExit(e);
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
