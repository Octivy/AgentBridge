$ErrorActionPreference = "Stop"

$targetBundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle"

if (-not (Test-Path $targetBundle)) {
    Write-Host "AgentBridge is not installed for the current Windows user."
    exit 0
}

Remove-Item -LiteralPath $targetBundle -Recurse -Force
Write-Host "AgentBridge has been removed. Restart AutoCAD to finish." -ForegroundColor Green
