param(
    [string]$Configuration = "Release",
    [string]$Platform = "x64",
    [string]$Framework = "net48",
    [string]$AutoCADInstallDir = "",
    [switch]$SkipRestore,
    [switch]$SkipService,
    [switch]$ForceRestartService,
    [int]$HealthCheckRetries = 8
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "copilot_backend"
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$serviceUrl = "http://127.0.0.1:8000/health"

function Test-BridgeHealth {
    try {
        $response = Invoke-RestMethod -Uri $serviceUrl -TimeoutSec 2
        return $response
    }
    catch {
        return $null
    }
}

function Get-BridgeServiceProcess {
    $pythonProcesses = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue
    if (-not $pythonProcesses) {
        return @()
    }

    return @($pythonProcesses | Where-Object {
        ($_.CommandLine -like "*uvicorn app:app*") -and ($_.CommandLine -like "*127.0.0.1*") -and ($_.CommandLine -like "*8000*")
    })
}

function Start-BridgeServiceWindow {
    if (-not (Test-Path $venvPython)) {
        throw "copilot_backend virtual environment not found. Run .\\restore-local-dev.ps1 first."
    }

    if ([string]::IsNullOrWhiteSpace($env:CADCOPILOT_LOCAL_BRIDGE_TOKEN)) {
        $bridgeConfigPath = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\agentbridge.config.json"
        if (Test-Path -LiteralPath $bridgeConfigPath) {
            $bridgeConfig = Get-Content -LiteralPath $bridgeConfigPath -Raw | ConvertFrom-Json
            $bridgeToken = [string]$bridgeConfig.LOCAL_BRIDGE_TOKEN
            if (-not [string]::IsNullOrWhiteSpace($bridgeToken)) {
                $env:CADCOPILOT_LOCAL_BRIDGE_TOKEN = $bridgeToken
            }
        }
    }

    $pythonPathParts = @($projectRoot, $backendRoot)
    if (-not [string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
        $pythonPathParts += $env:PYTHONPATH
    }
    $env:PYTHONPATH = $pythonPathParts -join [IO.Path]::PathSeparator

    $command = "Set-Location '$backendRoot'; .\\.venv\\Scripts\\python -m uvicorn app:app --host 127.0.0.1 --port 8000"
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) -WindowStyle Hidden -PassThru
    return $process
}

if (-not $SkipRestore) {
    & (Join-Path $projectRoot "restore-local-dev.ps1") -Configuration $Configuration -Platform $Platform -Framework $Framework -AutoCADInstallDir $AutoCADInstallDir
}

$health = Test-BridgeHealth

if ($ForceRestartService) {
    $existingProcesses = Get-BridgeServiceProcess
    foreach ($process in $existingProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $health = $null
}

if (-not $SkipService) {
    if ($health) {
        Write-Host "Copilot backend already healthy at $serviceUrl"
    }
    else {
        $startedProcess = Start-BridgeServiceWindow
        Write-Host "Started copilot backend window. PID: $($startedProcess.Id)"

        for ($attempt = 1; $attempt -le $HealthCheckRetries; $attempt++) {
            $health = Test-BridgeHealth
            if ($health) {
                break
            }

            Start-Sleep -Seconds 1
        }

        if (-not $health) {
            throw "Copilot backend did not become healthy at $serviceUrl"
        }
    }

    Write-Host "Backend health: status=$($health.status) provider=$($health.provider) model=$($health.model)"
}

Write-Host "Local development environment is ready."
Write-Host "Next: open AutoCAD 2024 and run AICHAT or AISNAPSHOT."
