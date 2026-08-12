param(
    [string]$Source = "",
    [switch]$AutoStart,
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
if (-not $Source) {
    $Source = Join-Path (Split-Path -Parent $PSScriptRoot) "AgentBridge"
}
$Source = (Resolve-Path $Source).Path
$target = Join-Path $env:LOCALAPPDATA "Programs\AgentBridge"

Write-Host "==> installing to $target"
if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item -LiteralPath $Source -Destination $target -Recurse

$exe = Join-Path $target "app\AgentBridge.Desktop.exe"
if (-not (Test-Path $exe)) { throw "AgentBridge.Desktop.exe not found: $exe" }

$shortcutDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $shortcutDir "AgentBridge.lnk"))
$lnk.TargetPath = $exe
$lnk.WorkingDirectory = $target
$lnk.Arguments = "`"$target`""
$lnk.IconLocation = "$exe,0"
$lnk.Save()

if ($AutoStart) {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    New-Item -Path $runKey -Force | Out-Null
    Set-ItemProperty -Path $runKey -Name "AgentBridge" -Value "`"$exe`" `"$target`""
    Write-Host "==> auto-start enabled"
}

if (-not $SkipSetup) {
    & (Join-Path $target "setup-backend.ps1") -BackendDir (Join-Path $target "copilot_backend")
}

Write-Host "==> install complete. Start menu: AgentBridge, or run $exe"
