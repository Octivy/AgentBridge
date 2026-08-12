param(
    [int]$McpRepeat = 20,
    [int]$ProviderRepeat = 10,
    [int]$BridgeRepeat = 20,
    [ValidateSet("auto", "openai", "anthropic", "deepseek", "minimax", "ollama")]
    [string]$Provider = "auto"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "copilot_backend\.venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    throw "Python virtual environment not found. Run restore-local-dev.ps1 first."
}

Push-Location $root
try {
    & $python "scripts\run_connector_acceptance.py" `
        --mcp-repeat $McpRepeat `
        --provider-repeat $ProviderRepeat `
        --bridge-repeat $BridgeRepeat `
        --provider $Provider `
        --report-dir "docs\validation"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
