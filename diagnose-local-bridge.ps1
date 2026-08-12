param(
    [string]$Configuration = "Release",
    [string]$Platform = "x64",
    [string]$Framework = "net48",
    [int]$LogTailLines = 200
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundleRoot = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle"
$bundleContents = Join-Path $bundleRoot "Contents"
$logPath = Join-Path $bundleContents "cadcopilot.log"
$configPath = Join-Path $bundleContents "agentbridge.config.json"
$serviceHealthUrl = "http://127.0.0.1:8000/health"
$localBridgeHealthUrl = "http://127.0.0.1:8765/health"

function Write-Section {
    param([string]$Title)

    Write-Host ""
    Write-Host "=== $Title ==="
}

function Invoke-HealthCheck {
    param([string]$Url)

    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 2
        return [pscustomobject]@{
            Url = $Url
            Reachable = $true
            Summary = ($response | ConvertTo-Json -Depth 8 -Compress)
            Error = $null
        }
    }
    catch {
        return [pscustomobject]@{
            Url = $Url
            Reachable = $false
            Summary = $null
            Error = $_.Exception.Message
        }
    }
}

function Get-BuildOutputDirectory {
    $candidates = @(
        (Join-Path $projectRoot "bin\$Platform\$Configuration\$Framework"),
        (Join-Path $projectRoot "bin\$Configuration\$Framework")
    )

    return $candidates | Where-Object { Test-Path (Join-Path $_ "AgentBridge.dll") } | Select-Object -First 1
}

function Get-DllInfo {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return [pscustomobject]@{
            Path = $Path
            Exists = $false
            Length = $null
            LastWriteTime = $null
            Version = $null
        }
    }

    $item = Get-Item $Path
    $version = $null
    try {
        $version = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($item.FullName).FileVersion
    }
    catch {
    }

    return [pscustomobject]@{
        Path = $item.FullName
        Exists = $true
        Length = $item.Length
        LastWriteTime = $item.LastWriteTime
        Version = $version
    }
}

function Get-ConfigSummary {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return [pscustomobject]@{
            Exists = $false
            ConnectionMode = $null
            ApiBaseUrl = $null
            LocalBridgeEnabled = $null
            LocalBridgeHost = $null
            LocalBridgePort = $null
            LocalBridgeTokenPresent = $null
            Error = $null
        }
    }

    try {
        $config = Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        return [pscustomobject]@{
            Exists = $true
            ConnectionMode = $config.CADCOPILOT_CONNECTION_MODE
            ApiBaseUrl = $config.CADCOPILOT_API_BASE_URL
            LocalBridgeEnabled = $config.LOCAL_BRIDGE_ENABLED
            LocalBridgeHost = $config.LOCAL_BRIDGE_HOST
            LocalBridgePort = $config.LOCAL_BRIDGE_PORT
            LocalBridgeTokenPresent = -not [string]::IsNullOrWhiteSpace($config.LOCAL_BRIDGE_TOKEN)
            Error = $null
        }
    }
    catch {
        return [pscustomobject]@{
            Exists = $true
            ConnectionMode = $null
            ApiBaseUrl = $null
            LocalBridgeEnabled = $null
            LocalBridgeHost = $null
            LocalBridgePort = $null
            LocalBridgeTokenPresent = $null
            Error = $_.Exception.Message
        }
    }
}

function Get-LogSummary {
    param(
        [string]$Path,
        [int]$TailLines
    )

    if (-not (Test-Path $Path)) {
        return [pscustomobject]@{
            Exists = $false
            HighlightLines = @()
            LastLines = @()
        }
    }

    $allLines = Get-Content $Path -Encoding UTF8
    $highlightPattern = 'LocalToolBridge|AgentBridge initialization completed|Failed to start LocalToolBridge'
    $highlightLines = @($allLines | Where-Object { $_ -match $highlightPattern })
    $lastLines = @($allLines | Select-Object -Last $TailLines)

    $bridgeStarted = @($allLines | Where-Object { $_ -match 'LocalToolBridge listening' }).Count -gt 0
    $bridgeStopped = @($allLines | Where-Object { $_ -match 'LocalToolBridge stopped' }).Count -gt 0

    return [pscustomobject]@{
        Exists = $true
        HighlightLines = $highlightLines
        LastLines = $lastLines
        BridgeStarted = $bridgeStarted
        BridgeStopped = $bridgeStopped
    }
}

$buildOutput = Get-BuildOutputDirectory
$bundleDllPath = Join-Path $bundleContents "AgentBridge.dll"
$buildDllPath = if ($buildOutput) { Join-Path $buildOutput "AgentBridge.dll" } else { $null }

$serviceHealth = Invoke-HealthCheck -Url $serviceHealthUrl
$localBridgeHealth = Invoke-HealthCheck -Url $localBridgeHealthUrl
$configSummary = Get-ConfigSummary -Path $configPath
$logSummary = Get-LogSummary -Path $logPath -TailLines $LogTailLines
$bundleDllInfo = Get-DllInfo -Path $bundleDllPath
$buildDllInfo = if ($buildDllPath) { Get-DllInfo -Path $buildDllPath } else {
    [pscustomobject]@{
        Path = $null
        Exists = $false
        Length = $null
        LastWriteTime = $null
        Version = $null
    }
}

$dllsMatch = $bundleDllInfo.Exists -and $buildDllInfo.Exists -and ($bundleDllInfo.Length -eq $buildDllInfo.Length) -and ($bundleDllInfo.LastWriteTime -eq $buildDllInfo.LastWriteTime)

Write-Section "Paths"
Write-Host "Project root: $projectRoot"
Write-Host "Bundle root:  $bundleRoot"
Write-Host "Log path:     $logPath"
Write-Host "Config path:  $configPath"

Write-Section "Health Checks"
Write-Host "Service 8000 reachable: $($serviceHealth.Reachable)"
if ($serviceHealth.Reachable) {
    Write-Host "Service 8000 response:  $($serviceHealth.Summary)"
}
else {
    Write-Host "Service 8000 error:     $($serviceHealth.Error)"
}

Write-Host "Local 8765 reachable:   $($localBridgeHealth.Reachable)"
if ($localBridgeHealth.Reachable) {
    Write-Host "Local 8765 response:    $($localBridgeHealth.Summary)"
}
else {
    Write-Host "Local 8765 error:       $($localBridgeHealth.Error)"
}

Write-Section "Bundle Config"
Write-Host "Config exists:           $($configSummary.Exists)"
if ($configSummary.Error) {
    Write-Host "Config parse error:      $($configSummary.Error)"
}
else {
    Write-Host "Connection mode:         $($configSummary.ConnectionMode)"
    Write-Host "Service URL:             $($configSummary.ApiBaseUrl)"
    Write-Host "LOCAL_BRIDGE_ENABLED:    $($configSummary.LocalBridgeEnabled)"
    Write-Host "LOCAL_BRIDGE_HOST:       $($configSummary.LocalBridgeHost)"
    Write-Host "LOCAL_BRIDGE_PORT:       $($configSummary.LocalBridgePort)"
    Write-Host "LOCAL_BRIDGE_TOKEN set:  $($configSummary.LocalBridgeTokenPresent)"
}

Write-Section "DLL Comparison"
Write-Host "Bundle DLL exists:       $($bundleDllInfo.Exists)"
Write-Host "Bundle DLL path:         $($bundleDllInfo.Path)"
Write-Host "Bundle DLL size:         $($bundleDllInfo.Length)"
Write-Host "Bundle DLL time:         $($bundleDllInfo.LastWriteTime)"
Write-Host "Bundle DLL version:      $($bundleDllInfo.Version)"
Write-Host "Build DLL exists:        $($buildDllInfo.Exists)"
Write-Host "Build DLL path:          $($buildDllInfo.Path)"
Write-Host "Build DLL size:          $($buildDllInfo.Length)"
Write-Host "Build DLL time:          $($buildDllInfo.LastWriteTime)"
Write-Host "Build DLL version:       $($buildDllInfo.Version)"
Write-Host "Bundle matches build:    $dllsMatch"

Write-Section "Relevant Log Lines"
if ($logSummary.Exists -and $logSummary.HighlightLines.Count -gt 0) {
    $logSummary.HighlightLines | ForEach-Object { Write-Host $_ }
}
elseif ($logSummary.Exists) {
    Write-Host "No matching LocalToolBridge lines found."
}
else {
    Write-Host "Log file not found."
}

Write-Section "Tail Log"
if ($logSummary.Exists) {
    $logSummary.LastLines | ForEach-Object { Write-Host $_ }
}
else {
    Write-Host "Log file not found."
}

$overallOk = $serviceHealth.Reachable -and $localBridgeHealth.Reachable -and $bundleDllInfo.Exists -and $buildDllInfo.Exists -and $dllsMatch

Write-Section "Summary"
Write-Host "Overall healthy:         $overallOk"
if (-not $dllsMatch) {
    Write-Host "Hint: bundle DLL and build DLL differ. Re-run .\install.ps1 after closing AutoCAD."
}
if ($configSummary.Exists -and -not $configSummary.Error -and [string]::IsNullOrWhiteSpace($configSummary.LocalBridgeEnabled) -and [string]::IsNullOrWhiteSpace($configSummary.LocalBridgeHost) -and [string]::IsNullOrWhiteSpace($configSummary.LocalBridgePort)) {
    Write-Host "Hint: LOCAL_BRIDGE_* is blank in config, so the plugin defaults apply: enabled=true, host=127.0.0.1, port=8765."
}
if (-not $localBridgeHealth.Reachable) {
    if ($logSummary.BridgeStarted -and $logSummary.BridgeStopped) {
        Write-Host "Hint: log shows the local bridge started successfully and later stopped. Check whether AutoCAD has already been closed."
    }
    elseif ($logSummary.BridgeStarted) {
        Write-Host "Hint: log shows the local bridge did start. If 8765 is now unreachable, confirm AutoCAD is still running and the plugin instance was not unloaded."
    }
    else {
        Write-Host "Hint: if AutoCAD is open but 8765 is unreachable, inspect the relevant log lines above first."
    }
}
if (-not $serviceHealth.Reachable) {
    Write-Host "Hint: 8000 is unavailable. Re-run .\start-local-dev.ps1 or restart the copilot_backend process."
}