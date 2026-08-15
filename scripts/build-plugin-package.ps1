param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [ValidateSet("2014", "2016", "2024")]
    [string]$AutoCADVersion = "2024",
    [string]$AutoCADInstallDir = "",
    [string]$OutputDirectory = "artifacts\releases",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$seriesByVersion = @{
    "2014" = "R19.1"
    "2016" = "R20.1"
    "2024" = "R24.3"
}
$targetSeries = $seriesByVersion[$AutoCADVersion]
if (-not $targetSeries) {
    throw "Unsupported AutoCAD version: $AutoCADVersion"
}

$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root "AgentBridge.csproj"
$packageXml = Join-Path $root "PackageContents.xml"
$releaseAssets = Join-Path $root "website\release-assets"
$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
}

if (-not $SkipBuild) {
    $buildArgs = @("build", $project, "-c", $Configuration, "-p:AutoCADVersion=$AutoCADVersion")
    if ($AutoCADInstallDir) {
        $buildArgs += "-p:AutoCADInstallDir=$AutoCADInstallDir"
    }
    & dotnet @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "AgentBridge build failed with exit code $LASTEXITCODE."
    }
}

$buildOutput = Join-Path $root "bin\$Configuration\net48"
$pluginDll = Join-Path $buildOutput "AgentBridge.dll"
$jsonDll = Join-Path $buildOutput "Newtonsoft.Json.dll"
$prompt = Join-Path $buildOutput "Resources\system_prompt.txt"
$autocadTools = Join-Path $buildOutput "Resources\autocad_tools.json"

foreach ($required in @($packageXml, $pluginDll, $jsonDll, $prompt, $autocadTools)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release file is missing: $required"
    }
}

[xml]$manifest = Get-Content -LiteralPath $packageXml -Raw
$version = [string]$manifest.ApplicationPackage.AppVersion
if ([string]::IsNullOrWhiteSpace($version)) {
    throw "PackageContents.xml does not contain AppVersion."
}

$seriesNodes = @($manifest.ApplicationPackage.RuntimeRequirements) +
    @($manifest.ApplicationPackage.Components.RuntimeRequirements)
foreach ($node in $seriesNodes) {
    $node.SetAttribute("SeriesMin", $targetSeries)
    $node.SetAttribute("SeriesMax", $targetSeries)
}

$stagingRoot = Join-Path $env:TEMP ("cadcopilot-release-" + [Guid]::NewGuid().ToString("N"))
$bundleRoot = Join-Path $stagingRoot "AgentBridge.bundle"
$bundleContents = Join-Path $bundleRoot "Contents"
$bundleResources = Join-Path $bundleContents "Resources"

New-Item -ItemType Directory -Path $bundleResources -Force | Out-Null
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$manifest.Save((Join-Path $bundleRoot "PackageContents.xml"))
Copy-Item -LiteralPath $pluginDll -Destination (Join-Path $bundleContents "AgentBridge.dll")
Copy-Item -LiteralPath $jsonDll -Destination (Join-Path $bundleContents "Newtonsoft.Json.dll")
Copy-Item -LiteralPath $prompt -Destination (Join-Path $bundleResources "system_prompt.txt")
Copy-Item -LiteralPath $autocadTools -Destination (Join-Path $bundleResources "autocad_tools.json")
Copy-Item -LiteralPath (Join-Path $root "agentbridge.config.template.json") -Destination (Join-Path $bundleContents "agentbridge.config.json")

foreach ($asset in @("Install-AgentBridge.ps1", "Uninstall-AgentBridge.ps1")) {
    $source = Join-Path $releaseAssets $asset
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Release asset is missing: $source"
    }
    $assetContent = Get-Content -LiteralPath $source -Raw
    $assetContent = $assetContent -replace "AutoCAD 2024", "AutoCAD $AutoCADVersion"
    Set-Content -LiteralPath (Join-Path $stagingRoot $asset) -Value $assetContent -Encoding UTF8
}

$installationGuide = Get-ChildItem -LiteralPath $releaseAssets -Filter "*.txt" -File |
    Select-Object -First 1
if (-not $installationGuide) {
    throw "Release installation guide is missing from: $releaseAssets"
}
Copy-Item -LiteralPath $installationGuide.FullName -Destination (Join-Path $stagingRoot $installationGuide.Name)

$fileName = "AgentBridge-$version-AutoCAD-$AutoCADVersion.zip"
$archivePath = Join-Path $outputRoot $fileName
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal
$archive = Get-Item -LiteralPath $archivePath
$sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()

$releaseManifest = [ordered]@{
    product = "AgentBridge"
    channel = "preview"
    version = $version
    built_at = (Get-Date).ToUniversalTime().ToString("o")
    target = [ordered]@{
        os = "Windows x64"
        host = "AutoCAD $AutoCADVersion"
        series = $targetSeries
        framework = ".NET Framework 4.8"
    }
    artifact = [ordered]@{
        file = $fileName
        size_bytes = $archive.Length
        sha256 = $sha256
    }
}

$manifestPath = Join-Path $outputRoot "latest.json"
$releaseManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[pscustomobject]@{
    Version = $version
    AutoCADVersion = $AutoCADVersion
    Series = $targetSeries
    Archive = $archive.FullName
    SizeBytes = $archive.Length
    Sha256 = $sha256
    Manifest = $manifestPath
}
