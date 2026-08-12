using System.Diagnostics;
using System.Net.Http;

namespace AgentBridge.Client;

/// <summary>
/// Resident tray client for AgentBridge. Owns the backend process, exposes a
/// tray menu (open panel / restart backend / exit) and opens the web panel at
/// <c>http://127.0.0.1:8000/ui</c>.
/// </summary>
internal static class Program
{
    private const string BackendHost = "127.0.0.1";
    private const int BackendPort = 8000;
    private static readonly string BackendUrl = $"http://{BackendHost}:{BackendPort}";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(3) };

    private static Process? _backend;
    private static NotifyIcon? _tray;
    private static string _repoRoot = "";
    private static string _logPath = "";

    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Length > 0 && !string.IsNullOrWhiteSpace(args[0]))
        {
            _repoRoot = Path.GetFullPath(args[0]);
        }
        else
        {
            _repoRoot = FindRepoRoot();
        }

        var appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var stateDir = Path.Combine(appData, "AgentBridge");
        Directory.CreateDirectory(stateDir);
        _logPath = Path.Combine(stateDir, "client.log");

        Log($"AgentBridge client starting. repo={_repoRoot}");
        StartBackend();

        _tray = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "AgentBridge",
            Visible = true,
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开面板", null, (_, _) => OpenPanel());
        menu.Items.Add("重启 backend", null, (_, _) => RestartBackend());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => Exit());
        _tray.ContextMenuStrip = menu;

        var timer = new System.Windows.Forms.Timer { Interval = 5000 };
        timer.Tick += (_, _) => _ = UpdateStatusAsync();
        timer.Start();
        _ = UpdateStatusAsync();

        Log("tray active");
        Application.Run();
    }

    private static async Task UpdateStatusAsync()
    {
        try
        {
            var response = await Http.GetAsync(BackendUrl + "/health");
            if (response.IsSuccessStatusCode && _tray is not null)
            {
                _tray.Text = "AgentBridge · 运行中";
                return;
            }
        }
        catch (HttpRequestException)
        {
            // backend not reachable yet
        }

        if (_backend is not null && _backend.HasExited)
        {
            Log("backend exited; restarting");
            StartBackend();
        }
        if (_tray is not null)
        {
            _tray.Text = "AgentBridge · 未连接";
        }
    }

    private static void RestartBackend()
    {
        StopBackend();
        StartBackend();
    }

    private static void StartBackend()
    {
        try
        {
            var backendDir = Path.Combine(_repoRoot, "copilot_backend");
            if (!Directory.Exists(backendDir))
            {
                Log($"backend directory not found: {backendDir}");
                return;
            }

            var python = ResolvePython(_repoRoot);
            if (string.IsNullOrWhiteSpace(python))
            {
                Log("python not found");
                return;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                WorkingDirectory = backendDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            startInfo.ArgumentList.Add("-m");
            startInfo.ArgumentList.Add("uvicorn");
            startInfo.ArgumentList.Add("app:app");
            startInfo.ArgumentList.Add("--host");
            startInfo.ArgumentList.Add(BackendHost);
            startInfo.ArgumentList.Add("--port");
            startInfo.ArgumentList.Add(BackendPort.ToString());

            _backend = Process.Start(startInfo);
            if (_backend is null)
            {
                Log("failed to start backend process");
                return;
            }
            Log($"backend started pid={_backend.Id}");
            _backend.OutputDataReceived += (_, e) => Log("backend: " + e.Data);
            _backend.ErrorDataReceived += (_, e) => Log("backend: " + e.Data);
            _backend.BeginOutputReadLine();
            _backend.BeginErrorReadLine();
        }
        catch (Exception ex)
        {
            Log("start backend failed: " + ex);
        }
    }

    private static void StopBackend()
    {
        if (_backend is not null && !_backend.HasExited)
        {
            try
            {
                _backend.Kill(entireProcessTree: true);
            }
            catch (Exception ex)
            {
                Log("stop backend failed: " + ex.Message);
            }
            _backend.WaitForExit(3000);
        }
        _backend = null;
    }

    private static string? ResolvePython(string repoRoot)
    {
        var candidates = new[]
        {
            Path.Combine(repoRoot, ".venv", "Scripts", "python.exe"),
            Path.Combine(repoRoot, "copilot_backend", ".venv", "Scripts", "python.exe"),
        };
        foreach (var candidate in candidates)
        {
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }
        return "python";
    }

    private static string FindRepoRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "AgentBridge.sln")))
            {
                return directory.FullName;
            }
            directory = directory.Parent;
        }
        return Directory.GetCurrentDirectory();
    }

    private static void OpenPanel()
    {
        try
        {
            Process.Start(new ProcessStartInfo(BackendUrl + "/ui") { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            Log("open panel failed: " + ex.Message);
        }
    }

    private static void Exit()
    {
        Log("client exiting");
        StopBackend();
        _tray?.Dispose();
        Application.Exit();
    }

    private static void Log(string message)
    {
        try
        {
            File.AppendAllText(_logPath, $"{DateTime.Now:O} {message}{Environment.NewLine}");
        }
        catch
        {
            // logging must never crash the client
        }
    }
}
