# AgentBridge DSH 插件 —— Python 依赖安装脚本（一次性）
#
# 用法：右键“使用 PowerShell 运行”，或：
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# 作用：把 AgentBridge 三个 MCP 服务器所需的 Python 依赖装进本机 Python 3.11。
# 插件自带全部后端代码（runtime/ 目录），唯一前置就是本脚本。

$ErrorActionPreference = 'Stop'

$python = $null
foreach ($candidate in @(
    (Get-Command python -ErrorAction SilentlyContinue),
    (Get-Command py -ErrorAction SilentlyContinue)
)) {
    if ($candidate) { $python = $candidate.Source; break }
}
if (-not $python) {
    Write-Host "未找到 Python。请先安装 Python 3.11 并勾选 Add to PATH。" -ForegroundColor Red
    exit 1
}
Write-Host "使用 Python: $python"

$requirements = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'requirements.txt'
& $python -m pip install --upgrade pip
& $python -m pip install -r $requirements

Write-Host "完成。插件已可用。" -ForegroundColor Green
