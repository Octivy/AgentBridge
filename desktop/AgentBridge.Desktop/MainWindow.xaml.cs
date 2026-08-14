using System.ComponentModel;
using System.Diagnostics;
using System.Windows;
using System.Windows.Forms;
using AgentBridge.Desktop.Services;
using Microsoft.Web.WebView2.Core;
using Application = System.Windows.Application;

namespace AgentBridge.Desktop;

public partial class MainWindow : Window
{
    private readonly BackendHost _backend;
    private readonly NotifyIcon _tray;
    private bool _allowClose;
    private bool _trayActive = true;

    public MainWindow()
    {
        InitializeComponent();

        _backend = new BackendHost();
        _backend.StateChanged += OnBackendStateChanged;

        _tray = new NotifyIcon
        {
            Icon = System.Drawing.SystemIcons.Application,
            Text = "AgentBridge",
            Visible = true,
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("显示主窗口", null, (_, _) => ShowMainWindow());
        menu.Items.Add("重启后端", null, (_, _) => _backend.Restart());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => Quit());
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => ShowMainWindow();

        RepoText.Text = _backend.RepoRoot;
        Loaded += async (_, _) => await InitializeBrowserAsync();
        Closed += (_, _) =>
        {
            _tray.Visible = false;
            _tray.Dispose();
            _backend.Dispose();
        };
    }

    private async Task InitializeBrowserAsync()
    {
        _backend.Start();
        try
        {
            await Browser.EnsureCoreWebView2Async();
            Browser.CoreWebView2.Settings.AreDevToolsEnabled = true;
            Browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            // 面板用 alert/confirm 呈现操作结果（连接测试、安装插件等），必须开启
            Browser.CoreWebView2.Settings.AreDefaultScriptDialogsEnabled = true;
            NavigateTo("overview");
        }
        catch (Exception ex)
        {
            StatusText.Text = "WebView2 初始化失败: " + ex.Message;
        }
    }

    private void OnBackendStateChanged(BackendState state, string detail)
    {
        Dispatcher.Invoke(() =>
        {
            StatusDot.Fill = state switch
            {
                BackendState.Running => (System.Windows.Media.Brush)FindResource("Ok"),
                BackendState.Starting => (System.Windows.Media.Brush)FindResource("Warn"),
                BackendState.Error => (System.Windows.Media.Brush)FindResource("Err"),
                _ => (System.Windows.Media.Brush)FindResource("Warn"),
            };
            StatusText.Text = state switch
            {
                BackendState.Running => $"后端运行中 · v{detail}",
                BackendState.Starting => string.IsNullOrWhiteSpace(detail) ? "正在连接后端…" : $"后端启动中 · {detail}",
                BackendState.Error => "后端异常: " + detail,
                _ => "后端已停止",
            };
        });
    }

    private void NavigateTo(string section)
    {
        Browser.CoreWebView2.Navigate(BackendHost.BackendUrl + "/ui#" + section);
    }

    private void BtnRestartBackend_Click(object sender, RoutedEventArgs e)
    {
        _backend.Restart();
    }

    private void BtnOpenExternal_Click(object sender, RoutedEventArgs e)
    {
        Process.Start(new ProcessStartInfo(BackendHost.BackendUrl + "/ui") { UseShellExecute = true });
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        if (!_allowClose && _trayActive)
        {
            e.Cancel = true;
            Hide();
            return;
        }
        _tray.Visible = false;
    }

    private void Window_StateChanged(object? sender, EventArgs e)
    {
        if (WindowState == WindowState.Minimized && _trayActive)
        {
            Hide();
        }
    }

    private void ShowMainWindow()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }

    private void Quit()
    {
        _allowClose = true;
        _trayActive = false;
        Application.Current.Shutdown();
    }
}
