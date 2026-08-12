param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root "desktop\AgentBridge.Desktop\AgentBridge.Desktop.csproj"
$dist = Join-Path $root "dist\AgentBridge"

if (Test-Path -LiteralPath $dist) {
    Remove-Item -LiteralPath $dist -Recurse -Force
}
New-Item -ItemType Directory -Path $dist -Force | Out-Null

Write-Host "==> publish desktop app ($Configuration)"
dotnet publish $project -c $Configuration -r win-x64 --self-contained false -o (Join-Path $dist "app") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

Write-Host "==> copy backend + cadmcp + scripts"
Copy-Item -LiteralPath (Join-Path $root "copilot_backend") -Destination $dist -Recurse
Copy-Item -LiteralPath (Join-Path $root "cadmcp") -Destination $dist -Recurse
Copy-Item -LiteralPath (Join-Path $root "scripts") -Destination $dist -Recurse -ErrorAction SilentlyContinue

$backend = Join-Path $dist "copilot_backend"
Get-ChildItem -Path $backend -Recurse -Directory -Include "__pycache__", ".pytest_cache", ".venv", ".ruff_cache" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $backend -Recurse -File -Include "*.pyc", "*.pyo" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "setup-backend.ps1") -Destination $dist -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install-desktop.ps1") -Destination $dist -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "start-agentbridge.ps1") -Destination $dist -Force

$readme = @(
    "AgentBridge portable bundle",
    "===========================",
    "1) Run setup-backend.ps1 once to prepare the backend Python environment.",
    "2) Double-click start-agentbridge.ps1 (auto-setup + launch), or install-desktop.ps1 to install locally.",
    "3) Use -AutoStart on install-desktop.ps1 to launch at sign-in."
)
Set-Content -LiteralPath (Join-Path $dist "README.txt") -Value $readme -Encoding UTF8

Write-Host "==> bundle ready: $dist"
