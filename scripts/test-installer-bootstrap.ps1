param(
    [string]$Version = "1.0.0",
    [string]$InstallDir = "",
    [int]$Port = 8000
)

<#
.SYNOPSIS
End-to-end installer bootstrap test: silent install to a user directory,
launch the desktop app, verify the backend answers /health from the bundled
Python runtime, then silent uninstall. No admin rights required (custom /DIR).
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $repoRoot "dist\AgentBridge-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    throw "setup not found: $setup (run scripts\pack-desktop-installer.ps1 -CompileWithIscc first)"
}
if ($Port -le 0 -or $Port -ge 65536) { throw "invalid port: $Port" }
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:TEMP "AgentBridge-Install-Test"
}
if (Test-Path -LiteralPath $InstallDir) { Remove-Item -LiteralPath $InstallDir -Recurse -Force }

Write-Host "[1/4] silent install to $InstallDir"
$args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$InstallDir`"")
$proc = Start-Process -FilePath $setup -ArgumentList $args -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "installer exited with code $($proc.ExitCode)" }

$exe = Join-Path $InstallDir "app\AgentBridge.Desktop.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "installed exe not found: $exe" }
$runtime = Join-Path $InstallDir "backend\runtime\python.exe"
if (-not (Test-Path -LiteralPath $runtime)) { throw "bundled runtime not found: $runtime" }

# Inno 静默安装器退出瞬间可能仍在释放文件句柄，立即启动会让 .NET 宿主
# 读不到程序集而静默退出；等待几秒消除竞态。
Start-Sleep -Seconds 3

Write-Host "[2/4] launch desktop app (starts backend with bundled runtime, port $Port)"
$env:AGENTBRIDGE_PORT = [string]$Port
# 从 exe 所在目录启动（不能从仓库根启动，否则会误用开发后端，掩盖安装布局问题）
# 偶发环境下 Start-Process 可能返回空 pid（未真正启动），重试最多 3 次。
$app = $null
for ($attempt = 1; $attempt -le 3; $attempt++) {
    $app = Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -PassThru
    if ($app -and $app.Id -gt 0) { break }
    Write-Host "  launch attempt $attempt returned no pid, retrying..."
    Start-Sleep -Seconds 2
}
if (-not $app -or $app.Id -le 0) { throw "failed to launch $exe" }
Write-Host "  app pid=$($app.Id)"

Write-Host "[3/4] wait for backend health..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if ($app.HasExited) {
        Write-Host "  app exited early, code=$($app.ExitCode)"
        break
    }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3
        Write-Host "backend health: status=$($health.status) version=$($health.version)"
        $ok = $true
        break
    } catch {
        Write-Host ("  waiting... ({0}s)" -f (($i + 1) * 2))
    }
}
if (-not $ok) {
    Write-Host "--- desktop.log tail ---"
    Get-Content (Join-Path $env:LOCALAPPDATA "AgentBridge\desktop.log") -Tail 10 -ErrorAction SilentlyContinue
    throw "backend did not become healthy within 60s"
}

Write-Host "[4/4] stop app and silent uninstall"
taskkill /IM AgentBridge.Desktop.exe /F 2>$null | Out-Null
Start-Sleep -Seconds 2
# 桌面壳被强杀时，后端 python 子进程会成为孤儿并锁住安装目录；按路径精确清理。
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$InstallDir*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$unins = Join-Path $InstallDir "unins000.exe"
if (Test-Path -LiteralPath $unins) {
    $uproc = Start-Process -FilePath $unins -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
    Write-Host "uninstaller exit code: $($uproc.ExitCode)"
}
Write-Host "bootstrap test PASSED"
