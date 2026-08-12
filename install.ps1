param(
    [string]$Configuration = "Release",
    [string]$Platform = "x64",
    [string]$Framework = "net48",
    [ValidateSet("2014", "2016", "2024")]
    [string]$AutoCADVersion = "2024"
)

$ErrorActionPreference = "Stop"

$seriesByVersion = @{
    "2014" = "R19.1"
    "2016" = "R20.1"
    "2024" = "R24.3"
}
$targetSeries = $seriesByVersion[$AutoCADVersion]

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildOutputCandidates = @(
    (Join-Path $projectRoot "bin\$Platform\$Configuration\$Framework"),
    (Join-Path $projectRoot "bin\$Configuration\$Framework")
)
$buildOutput = $buildOutputCandidates |
    Where-Object { Test-Path (Join-Path $_ "AgentBridge.dll") } |
    Sort-Object { (Get-Item (Join-Path $_ "AgentBridge.dll")).LastWriteTime } -Descending |
    Select-Object -First 1
$bundleRoot = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle"
$bundleContents = Join-Path $bundleRoot "Contents"
$configTarget = Join-Path $bundleContents "agentbridge.config.json"
$configBackup = $null

if (Test-Path $configTarget) {
    $configBackup = Join-Path $env:TEMP "agentbridge.config.backup.json"
    Copy-Item $configTarget $configBackup -Force
}

function Restore-ConfigBackup {
    if ($configBackup -and (Test-Path $configBackup)) {
        New-Item -ItemType Directory -Path $bundleContents -Force | Out-Null
        Copy-Item $configBackup $configTarget -Force
        Remove-Item $configBackup -Force
    }
}

trap {
    Restore-ConfigBackup
    throw
}

Write-Host "[1/5] Checking build output..."
if (-not $buildOutput) {
    throw "Build output not found. Checked: $($buildOutputCandidates -join ', ')"
}

Write-Host "[2/5] Recreating bundle directory..."
$bundleRemoved = $false
if (Test-Path $bundleRoot) {
    try {
        Remove-Item -Path $bundleRoot -Recurse -Force
        $bundleRemoved = $true
    }
    catch {
        Write-Warning "Bundle directory is in use. Falling back to in-place overwrite: $($_.Exception.Message)"
    }
}

New-Item -ItemType Directory -Path $bundleContents -Force | Out-Null

Write-Host "[3/5] Copying package files..."
[xml]$manifest = Get-Content -LiteralPath (Join-Path $projectRoot "PackageContents.xml") -Raw
$seriesNodes = @($manifest.ApplicationPackage.RuntimeRequirements) +
    @($manifest.ApplicationPackage.Components.RuntimeRequirements)
foreach ($node in $seriesNodes) {
    $node.SetAttribute("SeriesMin", $targetSeries)
    $node.SetAttribute("SeriesMax", $targetSeries)
}
$manifest.Save((Join-Path $bundleRoot "PackageContents.xml"))
Copy-Item (Join-Path $buildOutput "AgentBridge.dll") $bundleContents -Force
Copy-Item (Join-Path $buildOutput "Newtonsoft.Json.dll") $bundleContents -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $buildOutput "System.Net.Http.dll") $bundleContents -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $buildOutput "Resources") $bundleContents -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Native wall/door/window kernels are maintained as an independent product line and are not bundled."

if ($configBackup -and (Test-Path $configBackup)) {
    Write-Host "[4/5] Restoring existing config..."
    Restore-ConfigBackup
} else {
    Write-Host "[4/5] Creating default config..."
    Copy-Item (Join-Path $projectRoot "agentbridge.config.template.json") $configTarget
}

$config = Get-Content -LiteralPath $configTarget -Raw | ConvertFrom-Json
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
    Write-Host "Generated a random LocalToolBridge token."
}
$config | Add-Member -NotePropertyName LOCAL_BRIDGE_REQUIRE_TOKEN -NotePropertyValue "true" -Force
$config | Add-Member -NotePropertyName CONFIG_SCHEMA_VERSION -NotePropertyValue "2" -Force
$config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $configTarget -Encoding UTF8

Write-Host "[5/5] Done."
Write-Host "Bundle installed to: $bundleRoot"
Write-Host "Bundle targets AutoCAD $AutoCADVersion ($targetSeries)."
Write-Host "Next: edit $configTarget and set CADCOPILOT_API_BASE_URL if needed. The generated bridge token is loaded automatically by scripts/start-cadmcp.ps1."
