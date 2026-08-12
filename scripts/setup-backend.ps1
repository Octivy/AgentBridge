param(
    [string]$BackendDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $BackendDir) {
    $BackendDir = Join-Path (Split-Path -Parent $PSScriptRoot) "copilot_backend"
}
$BackendDir = (Resolve-Path $BackendDir).Path
$root = Split-Path -Parent $BackendDir

$python = "python"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "==> creating venv $root\.venv"
    & $python -m venv (Join-Path $root ".venv")
}
$python = $venvPython

Write-Host "==> installing backend dependencies"
& $python -m pip install --upgrade pip | Out-Null
& $python -m pip install -r (Join-Path $BackendDir "requirements.txt")
if (Test-Path (Join-Path $root "cadmcp\pyproject.toml")) {
    & $python -m pip install (Join-Path $root "cadmcp")
}
& $python -m pip install tomli_w

Write-Host "==> backend environment ready: $python"
