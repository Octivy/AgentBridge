param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$sourceBundle = Join-Path $PSScriptRoot "AgentBridge.bundle"
$targetBundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle"
$sourceContents = Join-Path $sourceBundle "Contents"
$targetContents = Join-Path $targetBundle "Contents"
$targetConfig = Join-Path $targetContents "agentbridge.config.json"
$configBackup = Join-Path $env:TEMP "agentbridge-config-$([Guid]::NewGuid().ToString('N')).json"

if (-not (Test-Path (Join-Path $sourceContents "AgentBridge.dll"))) {
    throw "The plugin payload is incomplete. Re-download the release package."
}

if (Test-Path $targetConfig) {
    Copy-Item -LiteralPath $targetConfig -Destination $configBackup -Force
}

try {
    if (Test-Path $targetBundle) {
        Remove-Item -LiteralPath $targetBundle -Recurse -Force
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $targetBundle) -Force | Out-Null
    Copy-Item -LiteralPath $sourceBundle -Destination $targetBundle -Recurse -Force

    if (Test-Path $configBackup) {
        Copy-Item -LiteralPath $configBackup -Destination $targetConfig -Force
    }

    $config = Get-Content -LiteralPath $targetConfig -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$config.LOCAL_BRIDGE_TOKEN)) {
        $tokenBytes = New-Object byte[] 32
        $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $random.GetBytes($tokenBytes)
        }
        finally {
            $random.Dispose()
        }
        $config.LOCAL_BRIDGE_TOKEN = [Convert]::ToBase64String($tokenBytes)
    }

    $config | Add-Member -NotePropertyName LOCAL_BRIDGE_REQUIRE_TOKEN -NotePropertyValue "true" -Force
    $config | Add-Member -NotePropertyName CONFIG_SCHEMA_VERSION -NotePropertyValue "2" -Force
    $config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $targetConfig -Encoding UTF8

    Get-ChildItem -LiteralPath $targetContents -Recurse -File |
        Unblock-File -ErrorAction SilentlyContinue
}
finally {
    if (Test-Path $configBackup) {
        Remove-Item -LiteralPath $configBackup -Force
    }
}

Write-Host ""
Write-Host "AgentBridge has been installed for the current Windows user." -ForegroundColor Green
Write-Host "Location: $targetBundle"
Write-Host "Next: restart AutoCAD 2024, then run TESTCOPILOT and AICHAT."
