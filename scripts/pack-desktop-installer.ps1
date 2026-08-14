param(
    [string]$Version = "1.0.0",
    [switch]$CompileWithIscc
)

<#
.SYNOPSIS
Assemble the installer staging tree and (optionally) compile the Inno Setup
installer.

Layout produced under dist\installer-stage:
    app\                     self-contained AgentBridge.Desktop (no .NET needed)
    backend\copilot_backend\ backend source (uvicorn app:app)
    backend\adapters\        host adapters (blender/sketchup/rhino)
    backend\scripts\         bridge launchers (start-cadmcp / start-hostmcp)
    backend\runtime\         embedded Python + dependencies (build-portable-runtime)
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $repoRoot "dist"
$stage = Join-Path $dist "installer-stage"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

# ---- 1. desktop app: self-contained publish (no .NET runtime dependency) ----
Write-Host "[1/4] dotnet publish desktop (self-contained win-x64)..."
dotnet publish (Join-Path $repoRoot "desktop\AgentBridge.Desktop\AgentBridge.Desktop.csproj") `
    -c Release -r win-x64 --self-contained true -o (Join-Path $stage "app")
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

# ---- 2. backend source ----
Write-Host "[2/4] copy backend source..."
Copy-Item -LiteralPath (Join-Path $repoRoot "copilot_backend") `
    -Destination (Join-Path $stage "backend\copilot_backend") -Recurse -Force
$backendDir = Join-Path $stage "backend\copilot_backend"
Get-ChildItem -LiteralPath $backendDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $backendDir -Recurse -Directory -Filter ".pytest_cache" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $backendDir -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "tests" -or $_.Name -eq ".env" -or ($_.Name -like "test_*.py") } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ---- 3. adapters + scripts (installed repo root = <install>\backend) ----
Write-Host "[3/4] copy adapters + scripts..."
Copy-Item -LiteralPath (Join-Path $repoRoot "adapters") `
    -Destination (Join-Path $stage "backend") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "scripts") `
    -Destination (Join-Path $stage "backend") -Recurse -Force

# ---- 4. embedded Python runtime ----
Write-Host "[4/4] build embedded runtime..."
& (Join-Path $repoRoot "scripts\build-portable-runtime.ps1") -OutDir (Join-Path $stage "backend\runtime")

# ---- 5. optionally compile the Inno Setup installer ----
if ($CompileWithIscc) {
    $iscc = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found. Install Inno Setup 6 or drop -CompileWithIscc." }

    # ChineseSimplified is an official Inno 6.4 translation; fetch it next to
    # the script when the local install lacks it.
    $issDir = Join-Path $repoRoot "desktop\installer"
    $isl = Join-Path $issDir "ChineseSimplified.isl"
    if (-not (Test-Path -LiteralPath $isl)) {
        Write-Host "Downloading ChineseSimplified.isl..."
        $islUrls = @(
            "https://cdn.jsdelivr.net/gh/jrsoftware/issrc@main/Files/Languages/ChineseSimplified.isl",
            "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl"
        )
        foreach ($islUrl in $islUrls) {
            & curl.exe -sL --connect-timeout 15 -o $isl $islUrl
            if ((Test-Path -LiteralPath $isl) -and (Get-Item -LiteralPath $isl).Length -gt 10KB) { break }
        }
        if (-not (Test-Path -LiteralPath $isl) -or (Get-Item -LiteralPath $isl).Length -le 10KB) {
            throw "failed to download ChineseSimplified.isl"
        }
    }

    $iss = Join-Path $issDir "agentbridge.iss"
    & $iscc "/DMyAppVersion=$Version" $iss
    if ($LASTEXITCODE -ne 0) { throw "ISCC compile failed" }
    Write-Host "setup.exe produced at $(Join-Path $dist ('AgentBridge-Setup-' + $Version + '.exe'))"
}

Write-Host "staging complete at $stage"
