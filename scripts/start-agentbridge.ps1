param(
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "app\AgentBridge.Desktop.exe"
$backend = Join-Path $root "copilot_backend"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "未找到 $exe（请先运行 pack-desktop.ps1 生成便携包）"
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not $SkipSetup -and -not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "==> 首次运行：初始化后端环境"
    & (Join-Path $root "setup-backend.ps1") -BackendDir $backend
}

Write-Host "==> 启动 AgentBridge 桌面客户端"
Start-Process -FilePath $exe -ArgumentList "`"$root`"" -WindowStyle Normal
