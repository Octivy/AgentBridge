param(
    [string]$Configuration = "Release",
    [string]$Platform = "x64",
    [string]$Framework = "net48",
    [string]$AutoCADInstallDir = "",
    [switch]$RecreateVenv,
    [switch]$SkipVenv,
    [switch]$SkipBuild,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "copilot_backend"
$venvRoot = Join-Path $backendRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    Write-Host "==> $Label"
    & $Action
}

function Resolve-PythonCommand {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        try {
            & $pyCommand.Source -3 --version | Out-Null
            return @($pyCommand.Source, "-3")
        }
        catch {
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return @($pythonCommand.Source)
    }

    throw "Python not found. Install Python 3, then rerun this script."
}

function Resolve-DotNetCommand {
    $dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
    if (-not $dotnetCommand) {
        throw "dotnet not found. Install .NET SDK, then rerun this script."
    }

    return $dotnetCommand.Source
}

function Test-AutoCADDirectory {
    param([string]$CandidatePath)

    if ([string]::IsNullOrWhiteSpace($CandidatePath)) {
        return $false
    }

    $requiredFiles = @(
        "acmgd.dll",
        "acdbmgd.dll",
        "accoremgd.dll",
        "AcWindows.dll"
    )

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path (Join-Path $CandidatePath $requiredFile))) {
            return $false
        }
    }

    return $true
}

function Resolve-AutoCADInstallDir {
    param([string]$PreferredPath)

    $candidates = @(
        $PreferredPath,
        $env:AUTOCAD_INSTALL_DIR,
        "D:\Program Files\Autodesk\AutoCAD 2024",
        "C:\Program Files\Autodesk\AutoCAD 2024"
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

    foreach ($candidate in $candidates) {
        if (Test-AutoCADDirectory -CandidatePath $candidate) {
            return $candidate
        }
    }

    throw "AutoCAD 2024 install directory not found. Pass -AutoCADInstallDir explicitly."
}

$resolvedAutoCADInstallDir = Resolve-AutoCADInstallDir -PreferredPath $AutoCADInstallDir
$dotnetCommand = Resolve-DotNetCommand

Write-Host "Using AutoCADInstallDir: $resolvedAutoCADInstallDir"

if (-not $SkipVenv) {
    $pythonCommand = Resolve-PythonCommand
    $pythonArgs = @()
    if ($pythonCommand.Count -gt 1) {
        $pythonArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
    }

    if ($RecreateVenv -and (Test-Path $venvRoot)) {
        Invoke-Step -Label "Removing existing copilot_backend/.venv" -Action {
            Remove-Item -Path $venvRoot -Recurse -Force
        }
    }

    if (-not (Test-Path $venvPython)) {
        Invoke-Step -Label "Creating copilot_backend/.venv" -Action {
            & $pythonCommand[0] @pythonArgs -m venv $venvRoot
        }

        Invoke-Step -Label "Installing copilot_backend dependencies" -Action {
            & $venvPython -m pip install --upgrade pip
            # pip skips the editable install when a same-name/same-version package
            # already exists (e.g. an older checkout of this project), silently
            # keeping the stale mapping. Uninstall first so the editable finder
            # always points at THIS checkout.
            & $venvPython -m pip uninstall -y cadmcp
            & $venvPython -m pip install --force-reinstall --no-deps -e "$projectRoot" -r (Join-Path $backendRoot "requirements.txt")
        }
    } else {
        Write-Host "==> copilot_backend/.venv already exists; skipping dependency install"
    }
}

if (-not (Test-Path (Join-Path $backendRoot ".env"))) {
    Write-Warning "copilot_backend/.env not found. The plugin can still build, but the backend will need a local MiniMax key before use."
}

if (-not $SkipBuild) {
    Invoke-Step -Label "Building AgentBridge" -Action {
        & $dotnetCommand build (Join-Path $projectRoot "AgentBridge.sln") -c $Configuration -p:Platform=$Platform -p:AutoCADInstallDir=$resolvedAutoCADInstallDir
    }
}

if (-not $SkipInstall) {
    Invoke-Step -Label "Installing AutoCAD bundle" -Action {
        & (Join-Path $projectRoot "install.ps1") -Configuration $Configuration -Platform $Platform -Framework $Framework
    }
}

Write-Host "==> Ready"
Write-Host "Start copilot backend: .\\copilot_backend\\.venv\\Scripts\\python -m uvicorn app:app --host 127.0.0.1 --port 8000"
Write-Host "Health check: curl http://127.0.0.1:8000/health"
