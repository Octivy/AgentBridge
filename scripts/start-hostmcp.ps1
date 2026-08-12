param(
    [ValidateSet("stdio", "sse", "streamable-http")]
    [string]$Transport = "stdio"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "copilot_backend"

$candidates = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $backendRoot ".venv\Scripts\python.exe")
)
$python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    }
}
if (-not $python) {
    throw "Python was not found. Create .venv or copilot_backend/.venv first."
}

$registryDir = $env:HOSTMCP_REGISTRY_DIR
if ([string]::IsNullOrWhiteSpace($registryDir)) {
    $registryDir = Join-Path $env:LOCALAPPDATA "AgentBridge\hosts"
}

Push-Location -LiteralPath $backendRoot
try {
    & $python -m host_mcp --transport $Transport --registry-dir $registryDir
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
