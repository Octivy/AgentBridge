param(
    [string]$PythonVersion = "3.11.9",
    [string]$OutDir = ""
)

<#
.SYNOPSIS
Build a portable, self-contained Python runtime for the AgentBridge installer.

Layout produced (under $OutDir):
    python.exe / python311.dll / vcruntime*.dll
    python311.zip          (stdlib)
    python311._pth         (patched to include Lib\site-packages + import site)
    Lib\site-packages\     (dependencies copied from the local Python 3.11,
                            plus the repo's own cadmcp package)

The installed machine needs NO Python installed: the desktop shell launches
<install>\backend\runtime\python.exe directly.
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $repoRoot "dist\runtime"
}

# ---- 1. find a source Python 3.11 to harvest site-packages from ----
$basePython = $null
$candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    (Join-Path $env:ProgramFiles "Python311\python.exe")
)
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { $basePython = $candidate; break }
}
if (-not $basePython) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $basePython = $cmd.Source }
}
if (-not $basePython) {
    throw "Python 3.11 not found (needed as the dependency source). Install Python 3.11 first."
}
$baseRoot = Split-Path -Parent $basePython
$sourceSp = Join-Path $baseRoot "Lib\site-packages"
if (-not (Test-Path $sourceSp)) { throw "site-packages not found: $sourceSp" }
Write-Host "Harvesting site-packages from $baseRoot"

# ---- 2. fetch the official embeddable package (cached) ----
$downloads = Join-Path $repoRoot "dist\downloads"
New-Item -ItemType Directory -Force -Path $downloads | Out-Null
$zipUrls = @(
    "https://mirrors.huaweicloud.com/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip",
    "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
)
$zipPath = Join-Path $downloads "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -lt 8MB) {
    foreach ($zipUrl in $zipUrls) {
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Write-Host "Downloading $zipUrl"
        & curl.exe -L --retry 3 --retry-all-errors --connect-timeout 15 -o $zipPath $zipUrl
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $zipPath) -and (Get-Item -LiteralPath $zipPath).Length -ge 8MB) {
            break
        }
    }
    if (-not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -lt 8MB) {
        throw "download failed (tried all mirrors)"
    }
}

# ---- 3. extract ----
if (Test-Path -LiteralPath $OutDir) { Remove-Item -LiteralPath $OutDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Expand-Archive -LiteralPath $zipPath -DestinationPath $OutDir -Force

# ---- 4. copy site-packages ----
$targetSp = Join-Path $OutDir "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $targetSp | Out-Null
Copy-Item -Path (Join-Path $sourceSp "*") -Destination $targetSp -Recurse -Force

# Remove machine-specific leftovers: editable-install hooks point at H:\ paths.
# Other *.pth files (pywin32 etc.) are relative to site-packages and must stay.
Get-ChildItem -LiteralPath $targetSp -Filter "__editable*" -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $targetSp -Filter "cadmcp-*.dist-info" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# Prune bulky test/doc folders to keep the installer small.
Get-ChildItem -LiteralPath $targetSp -Directory | ForEach-Object {
    foreach ($sub in @("tests", "test", "docs")) {
        $path = Join-Path $_.FullName $sub
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
Get-ChildItem -LiteralPath $targetSp -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# ---- 5. bundle the repo's own cadmcp package ----
$repoCadMcp = Join-Path $repoRoot "cadmcp"
if (-not (Test-Path -LiteralPath $repoCadMcp)) { throw "repo cadmcp not found: $repoCadMcp" }
Copy-Item -LiteralPath $repoCadMcp -Destination (Join-Path $targetSp "cadmcp") -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $targetSp "cadmcp") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# ---- 6. patch python311._pth to enable site-packages ----
$pth = Join-Path $OutDir "python311._pth"
Set-Content -LiteralPath $pth -Encoding ASCII -Value @(
    "python311.zip"
    "."
    "Lib\site-packages"
    "import site"
)

# ---- 7. sanity check: bundled python imports the core stack ----
$checkCode = "import sys; import fastapi, uvicorn, pydantic, httpx, mcp, cadmcp; print('runtime ok', sys.version.split()[0])"
& (Join-Path $OutDir "python.exe") -c $checkCode
if ($LASTEXITCODE -ne 0) { throw "runtime self-check failed" }

Write-Host "runtime ready at $OutDir"
