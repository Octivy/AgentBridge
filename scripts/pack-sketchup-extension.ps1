param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$adapterDir = Join-Path $root "adapters\sketchup"
$dist = Join-Path $root "dist\SketchUp"
New-Item -ItemType Directory -Path $dist -Force | Out-Null

$tmp = Join-Path $env:TEMP ("ab-skp-ext-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $adapterDir "cadcopilot_extension.rb") -Destination $tmp
Copy-Item -LiteralPath (Join-Path $adapterDir "cadcopilot_host.rb") -Destination $tmp

$zip = Join-Path $dist "AgentBridge-Host-$Version.zip"
$rbz = Join-Path $dist "AgentBridge-Host-$Version.rbz"
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
if (Test-Path -LiteralPath $rbz) {
    Remove-Item -LiteralPath $rbz -Force
}
Compress-Archive -Path (Join-Path $tmp "*") -DestinationPath $zip -CompressionLevel Optimal
Remove-Item -LiteralPath $tmp -Recurse -Force
Move-Item -LiteralPath $zip -Destination $rbz -Force

Write-Host "==> SketchUp extension ready: $rbz"
