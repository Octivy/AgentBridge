param(
    [string]$OutputPath,
    [switch]$IncludeGitMetadata
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectName = Split-Path -Leaf $projectRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $parentDir = Split-Path -Parent $projectRoot
    $OutputPath = Join-Path $parentDir ($projectName + "-handoff-" + $timestamp + ".zip")
}

$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

$excludedDirectories = @(
    "bin",
    "obj",
    ".vs",
    "copilot_backend/.venv",
    "copilot_backend/__pycache__"
)

if (-not $IncludeGitMetadata) {
    $excludedDirectories += ".git"
}

$excludedFiles = @(
    "copilot_backend/.env",
    "agentbridge.config.json"
)

$excludedExtensions = @(
    ".log",
    ".pdb",
    ".suo",
    ".user"
)

function Test-ExcludedPath {
    param(
        [string]$RelativePath,
        [bool]$IsDirectory
    )

    $normalizedPath = $RelativePath.Replace("\", "/").TrimStart("/")

    foreach ($directory in $excludedDirectories) {
        $normalizedDirectory = $directory.Replace("\", "/").TrimStart("/")
        if ($normalizedPath -eq $normalizedDirectory -or $normalizedPath.StartsWith($normalizedDirectory + "/", [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    if (-not $IsDirectory) {
        foreach ($file in $excludedFiles) {
            $normalizedFile = $file.Replace("\", "/").TrimStart("/")
            if ($normalizedPath.Equals($normalizedFile, [System.StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }

        $extension = [System.IO.Path]::GetExtension($normalizedPath)
        if ($excludedExtensions -contains $extension) {
            return $true
        }
    }

    return $false
}

Add-Type -AssemblyName System.IO.Compression.FileSystem

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cadcopilot-handoff-" + [System.Guid]::NewGuid().ToString("N"))
$stagingProjectRoot = Join-Path $stagingRoot $projectName

try {
    New-Item -ItemType Directory -Path $stagingProjectRoot -Force | Out-Null

    Get-ChildItem -Path $projectRoot -Recurse -Force | ForEach-Object {
        $fullPath = $_.FullName
        $relativePath = $fullPath.Substring($projectRoot.Length).TrimStart("\\")

        if ([string]::IsNullOrWhiteSpace($relativePath)) {
            return
        }

        if (Test-ExcludedPath -RelativePath $relativePath -IsDirectory $_.PSIsContainer) {
            return
        }

        $targetPath = Join-Path $stagingProjectRoot $relativePath
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
            return
        }

        $targetDir = Split-Path -Parent $targetPath
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        Copy-Item -Path $fullPath -Destination $targetPath -Force
    }

    if (Test-Path $OutputPath) {
        Remove-Item -Path $OutputPath -Force
    }

    [System.IO.Compression.ZipFile]::CreateFromDirectory($stagingProjectRoot, $OutputPath)

    Write-Host "Handoff package created: $OutputPath"
    Write-Host "Next: copy this zip to the other machine, unzip it, then run .\restore-local-dev.ps1"
}
finally {
    if (Test-Path $stagingRoot) {
        Remove-Item -Path $stagingRoot -Recurse -Force
    }
}