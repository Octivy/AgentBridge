param(
    [datetime]$Date = (Get-Date),
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$docsRoot = Join-Path $projectRoot "docs"
$handoffTemplatePath = Join-Path $docsRoot "handoff-template.md"
$developmentLogTemplatePath = Join-Path $docsRoot "development-log-template.md"

if (-not (Test-Path $handoffTemplatePath)) {
    throw "Template not found: $handoffTemplatePath"
}

if (-not (Test-Path $developmentLogTemplatePath)) {
    throw "Template not found: $developmentLogTemplatePath"
}

$dateText = $Date.ToString("yyyy-MM-dd")
$handoffPath = Join-Path $docsRoot ("handoff-" + $dateText + ".md")
$developmentLogPath = Join-Path $docsRoot ("development-log-" + $dateText + ".md")

function Ensure-FileFromTemplate {
    param(
        [string]$TemplatePath,
        [string]$TargetPath,
        [string]$Label,
        [switch]$IncludeMachineName
    )

    if (Test-Path $TargetPath) {
        Write-Host "Using existing $Label file: $TargetPath"
        return
    }

    $templateContent = Get-Content $TemplatePath -Raw -Encoding UTF8
    $templateContent = $templateContent.Replace("YYYY-MM-DD", $dateText)

    if ($IncludeMachineName) {
        $templateContent = $templateContent.Replace("机器名：", "机器名：" + $env:COMPUTERNAME)
    }

    Set-Content -Path $TargetPath -Value $templateContent -Encoding UTF8
    Write-Host "Created $Label file: $TargetPath"
}

Ensure-FileFromTemplate -TemplatePath $handoffTemplatePath -TargetPath $handoffPath -Label "handoff" -IncludeMachineName
Ensure-FileFromTemplate -TemplatePath $developmentLogTemplatePath -TargetPath $developmentLogPath -Label "development log"

if ($NoOpen) {
    return
}

$codeCommand = Get-Command code -ErrorAction SilentlyContinue
if ($codeCommand) {
    & $codeCommand.Source -r $handoffPath | Out-Null
    if (Test-Path $developmentLogPath) {
        & $codeCommand.Source -r $developmentLogPath | Out-Null
    }

    return
}

Invoke-Item $handoffPath
if (Test-Path $developmentLogPath) {
    Invoke-Item $developmentLogPath
}