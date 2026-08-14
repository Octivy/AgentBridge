using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;

namespace AgentBridge.Desktop.Services;

/// <summary>
/// Owns the AgentBridge backend (FastAPI/uvicorn) process: resolves the repo
/// and Python runtime, starts/stops the backend, and monitors /health so the
/// shell can show live status and restart on crash.
/// </summary>
public sealed class BackendHost : IDisposable
{
    public const string BackendHostAddress = "127.0.0.1";
    public const int DefaultBackendPort = 8000;

    /// <summary>Actual backend port: AGENTBRIDGE_PORT env -> client.json -> 8000.</summary>
    public static readonly int BackendPort = ResolveBackendPort();
    public static readonly string BackendUrl = $"http://{BackendHostAddress}:{BackendPort}";

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(3) };

    private readonly object _gate = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly string _repoRoot;
    private readonly string _logPath;
    private Process? _process;
    private System.Threading.Timer? _timer;
    private volatile BackendState _state = BackendState.Stopped;
    private string _version = "";
    private bool _autoStarted;

    public event Action<BackendState, string>? StateChanged;

    public string RepoRoot => _repoRoot;
    public BackendState State => _state;
    public string Version => _version;

    public BackendHost(string? explicitRepoRoot = null)
    {
        _repoRoot = string.IsNullOrWhiteSpace(explicitRepoRoot) ? FindRepoRoot() : Path.GetFullPath(explicitRepoRoot);
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var stateDir = Path.Combine(appData, "AgentBridge");
        Directory.CreateDirectory(stateDir);
        _logPath = Path.Combine(stateDir, "desktop.log");
        Log($"AgentBridge.Desktop starting. repo={_repoRoot}");
    }

    public void Start()
    {
        lock (_gate)
        {
            if (_process is { HasExited: false } || _state == BackendState.Starting)
            {
                return;
            }
            _timer ??= new System.Threading.Timer(_ => PollHealth(), null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3));
            EnsureBackendRunning();
        }
    }

    public void Restart()
    {
        lock (_gate)
        {
            StopBackend();
            EnsureBackendRunning();
        }
    }

    public void Stop()
    {
        lock (_gate)
        {
            StopBackend();
            _timer?.Dispose();
            _timer = null;
        }
    }

    public void Dispose()
    {
        _cts.Cancel();
        Stop();
        Http.Dispose();
        _cts.Dispose();
    }

    private void EnsureBackendRunning()
    {
        var backendDir = ResolveBackendDir(_repoRoot);
        if (!Directory.Exists(backendDir))
        {
            SetState(BackendState.Error, $"backend directory not found: {backendDir}");
            return;
        }

        var python = ResolvePython(backendDir);
        if (string.IsNullOrWhiteSpace(python))
        {
            SetState(BackendState.Error, "python not found (tried .venv, bundled runtime and system python)");
            return;
        }

        try
        {
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
            startInfo.ArgumentList.Add(BackendHostAddress);
            startInfo.ArgumentList.Add("--port");
            startInfo.ArgumentList.Add(BackendPort.ToString());

            _process = Process.Start(startInfo);
            if (_process is null)
            {
                SetState(BackendState.Error, "failed to start backend process");
                return;
            }

            _process.OutputDataReceived += (_, e) => Log("backend: " + e.Data);
            _process.ErrorDataReceived += (_, e) => Log("backend: " + e.Data);
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
            SetState(BackendState.Starting, $"backend pid={_process.Id}");
            Log($"backend started pid={_process.Id}");
        }
        catch (Exception ex)
        {
            SetState(BackendState.Error, "start backend failed: " + ex.Message);
            Log("start backend failed: " + ex);
        }
    }

    private void StopBackend()
    {
        if (_process is not null)
        {
            try
            {
                _process.Kill(entireProcessTree: true);
                _process.WaitForExit(3000);
            }
            catch (Exception ex)
            {
                Log("stop backend failed: " + ex.Message);
            }
            _process = null;
        }
        SetState(BackendState.Stopped, "");
    }

    private async void PollHealth()
    {
        try
        {
            var response = await Http.GetAsync(BackendUrl + "/health", _cts.Token);
            if (response.IsSuccessStatusCode)
            {
                var payload = await response.Content.ReadAsStringAsync(_cts.Token);
                var version = ExtractVersion(payload);
                if (_state != BackendState.Running || _version != version)
                {
                    _version = version;
                    SetState(BackendState.Running, version);
                    _ = TriggerAutoStartAsync();
                }
                return;
            }
        }
        catch (Exception) when (_cts.IsCancellationRequested)
        {
            return;
        }
        catch (Exception)
        {
            // backend not reachable yet
        }

        lock (_gate)
        {
            if (_process is { HasExited: true } && _state != BackendState.Starting)
            {
                Log("backend exited; restarting");
                EnsureBackendRunning();
                return;
            }
        }
        if (_state is BackendState.Running or BackendState.Starting)
        {
            SetState(BackendState.Starting, _version);
        }
    }

    private static string ExtractVersion(string healthJson)
    {
        const string marker = "\"version\":";
        var index = healthJson.IndexOf(marker, StringComparison.Ordinal);
        if (index < 0)
        {
            return "";
        }
        var start = index + marker.Length;
        var end = healthJson.IndexOfAny(new[] { '"', ',', '}' }, start);
        if (end <= start)
        {
            return "";
        }
        return healthJson[start..end].Trim('"', ' ', ':');
    }

    private async Task TriggerAutoStartAsync()
    {
        if (_autoStarted)
        {
            return;
        }
        _autoStarted = true;
        try
        {
            using var response = await Http.PostAsync(BackendUrl + "/config/hosts/auto-start", null, _cts.Token);
            Log($"auto-start hosts: {(int)response.StatusCode}");
        }
        catch (Exception ex)
        {
            Log("auto-start hosts failed: " + ex.Message);
        }
    }

    private static string? ResolvePython(string backendDir)
    {
        var candidates = new[]
        {
            Path.Combine(backendDir, ".venv", "Scripts", "python.exe"),
            Path.Combine(Path.GetDirectoryName(backendDir) ?? backendDir, ".venv", "Scripts", "python.exe"),
            // Installed layout: <install>\backend\runtime\python.exe (embedded runtime
            // bundled by the Inno Setup installer; no system Python required).
            Path.Combine(Path.GetDirectoryName(backendDir) ?? backendDir, "runtime", "python.exe"),
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

    private static int ResolveBackendPort()
    {
        // 1. explicit environment override (AGENTBRIDGE_PORT=8210)
        if (TryParsePort(Environment.GetEnvironmentVariable("AGENTBRIDGE_PORT"), out var port))
        {
            return port;
        }
        // 2. persistent client config (%LOCALAPPDATA%\AgentBridge\client.json)
        try
        {
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var configPath = Path.Combine(appData, "AgentBridge", "client.json");
            if (File.Exists(configPath))
            {
                using var document = JsonDocument.Parse(File.ReadAllText(configPath));
                if (document.RootElement.TryGetProperty("backend_port", out var element) &&
                    element.TryGetInt32(out var configured) &&
                    configured is > 0 and < 65536)
                {
                    return configured;
                }
            }
        }
        catch
        {
            // config read errors fall back to the default port
        }
        return DefaultBackendPort;
    }

    private static bool TryParsePort(string? value, out int port)
    {
        port = 0;
        return int.TryParse(value, out port) && port is > 0 and < 65536;
    }

    private static string ResolveBackendDir(string repoRoot)
    {
        var candidates = new[]
        {
            Path.Combine(repoRoot, "copilot_backend"),
            Path.Combine(repoRoot, "backend", "copilot_backend"),
        };
        foreach (var candidate in candidates)
        {
            if (Directory.Exists(candidate))
            {
                return candidate;
            }
        }
        return candidates[0];
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
        var bundled = Path.Combine(AppContext.BaseDirectory, "backend", "copilot_backend");
        if (Directory.Exists(bundled))
        {
            return AppContext.BaseDirectory;
        }
        return Directory.GetCurrentDirectory();
    }

    private void SetState(BackendState state, string detail)
    {
        _state = state;
        StateChanged?.Invoke(state, detail);
    }

    private void Log(string message)
    {
        try
        {
            File.AppendAllText(_logPath, $"{DateTime.Now:O} {message}{Environment.NewLine}");
        }
        catch
        {
            // logging must never crash the host
        }
    }
}

public enum BackendState
{
    Stopped,
    Starting,
    Running,
    Error,
}
