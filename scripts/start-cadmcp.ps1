param(
    [ValidateSet("stdio", "sse", "streamable-http")]
    [string]$Transport = "stdio"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$candidates = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $projectRoot "copilot_backend\.venv\Scripts\python.exe"),
    (Join-Path $projectRoot "runtime\python.exe")
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

if ([string]::IsNullOrWhiteSpace($env:CADMCP_BRIDGE_TOKEN)) {
    $configCandidates = @(
        (Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\agentbridge.config.json"),
        (Join-Path $projectRoot "agentbridge.config.json")
    )
    $bridgeConfigPath = $configCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($bridgeConfigPath) {
        try {
            $bridgeConfig = Get-Content -LiteralPath $bridgeConfigPath -Raw | ConvertFrom-Json
            $bridgeToken = [string]$bridgeConfig.LOCAL_BRIDGE_TOKEN
            if (-not [string]::IsNullOrWhiteSpace($bridgeToken)) {
                $env:CADMCP_BRIDGE_TOKEN = $bridgeToken
                $env:CADCOPILOT_LOCAL_BRIDGE_TOKEN = $bridgeToken
                if ([string]::IsNullOrWhiteSpace($env:CADMCP_PERMISSION_SECRET)) {
                    $env:CADMCP_PERMISSION_SECRET = $bridgeToken
                }
            }
        }
        catch {
            throw "Failed to load LocalToolBridge token from $bridgeConfigPath`: $($_.Exception.Message)"
        }
    }
}

Set-Location -LiteralPath $projectRoot
& $python -m cadmcp --transport $Transport
exit $LASTEXITCODE
