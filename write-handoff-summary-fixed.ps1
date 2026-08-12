param(

    [string]$OutputPath = "",

    [switch]$Overwrite

)



$ErrorActionPreference = "Stop"



$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$today = Get-Date -Format "yyyy-MM-dd"



if ([string]::IsNullOrWhiteSpace($OutputPath)) {

    $OutputPath = Join-Path $projectRoot "docs\handoff-$today.md"

}



$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)



function Resolve-AutoCADInstallDir {

    $candidates = @(

        $env:AUTOCAD_INSTALL_DIR,

        "D:\Program Files\Autodesk\AutoCAD 2024",

        "C:\Program Files\Autodesk\AutoCAD 2024",

    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique



    foreach ($candidate in $candidates) {

        $requiredFiles = @("acmgd.dll", "acdbmgd.dll", "accoremgd.dll", "AcWindows.dll")

        $allPresent = $true

        foreach ($requiredFile in $requiredFiles) {

            if (-not (Test-Path (Join-Path $candidate $requiredFile))) {

                $allPresent = $false

                break

            }

        }



        if ($allPresent) {

            return $candidate

        }

    }



    return "未检测到"

}



function Get-BuildStatus {

    $buildCandidates = (@(

        (Join-Path $projectRoot "bin\x64\Release\net48\AgentBridge.dll"),

        (Join-Path $projectRoot "bin\Release\net48\AgentBridge.dll"),

        (Join-Path $projectRoot "bin\Debug\net48\AgentBridge.dll")))



    $buildOutput = $buildCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $buildOutput) {

        return "未检测到构建产物"

    }



    $item = Get-Item $buildOutput

    return "已检测到: $buildOutput (更新时间: $($item.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')))"

}



function Get-BundleStatus {

    $configPath = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\agentbridge.config.json"

    $dllPath = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\AgentBridge.dll"



    if (-not (Test-Path $dllPath)) {

        return "Bundle 未安装"

    }



    $dllTime = (Get-Item $dllPath).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')

    if (-not (Test-Path $configPath)) {

        return "Bundle 已安装，DLL 更新时间: $dllTime，未检测到配置文件"

    }



    $config = Get-Content $configPath | ConvertFrom-Json

    return "Bundle 已安装，DLL 更新时间: $dllTime，模式: $($config.CADCOPILOT_CONNECTION_MODE)，服务地址: $($config.CADCOPILOT_API_BASE_URL)"

}



function Get-BridgeHealthStatus {

    try {

        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2

        return "健康: status=$($response.status), provider=$($response.provider), model=$($response.model)"

    }

    catch {

        return "未连通"

    }

}



function Get-GitStatusSummary {

    $gitCommand = Get-Command git -ErrorAction SilentlyContinue

    if (-not $gitCommand) {

        return "git 未安装"

    }



    Push-Location $projectRoot

    try {

        & $gitCommand.Source rev-parse --is-inside-work-tree 2>$null | Out-Null

        if ($LASTEXITCODE -ne 0) {

            return "当前目录不是 git 仓库"

        }



        $branch = (& $gitCommand.Source branch --show-current 2>$null).Trim()

        $statusLines = @(& $gitCommand.Source status --short 2>$null)

        if ([string]::IsNullOrWhiteSpace($branch)) {

            $branch = "detached"

        }



        return "分支: $branch，未提交变更数: $($statusLines.Count)"

    }

    finally {

        Pop-Location

    }

}



if ((Test-Path $OutputPath) -and (-not $Overwrite)) {

    throw "Output already exists: $OutputPath. Use -Overwrite to replace it."

}



$content = @"

# AgentBridge 交接摘要



更新时间：$today

机器名：$env:COMPUTERNAME



## 当前状态



- 已完成：

- 未完成：



## 下一步



- 



## 本机验证



- AutoCADInstallDir: $(Resolve-AutoCADInstallDir)

- build: $(Get-BuildStatus)

- bundle: $(Get-BundleStatus)

- copilot_backend: $(Get-BridgeHealthStatus)



## 代码仓库状态



- $(Get-GitStatusSummary)



## 机器差异



- 这台机器特有的 AutoCAD 版本或安装目录：

- 这台机器特有的配置或限制：



## 备注



- 

"@



$outputDir = Split-Path -Parent $OutputPath

if (-not (Test-Path $outputDir)) {

    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

}



Set-Content -Path $OutputPath -Value $content -Encoding UTF8

Write-Host "Handoff summary written to: $OutputPath"

