@echo off
rem AgentBridge 网页面板启动器（使用插件内置 Python，无需额外安装）
rem 双击运行：会在本机启动面板后端，并自动打开浏览器。
setlocal
set "RUNTIME=%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%RUNTIME%
set "PANEL_PORT=8020"
echo 正在启动 AgentBridge 面板（http://127.0.0.1:%PANEL_PORT%/ui）...
echo 关闭此窗口即停止面板。
start "" /min cmd /c "timeout /t 4 >nul & start "" http://127.0.0.1:%PANEL_PORT%/ui"
"%RUNTIME%python\python.exe" -m uvicorn app:app --app-dir "%RUNTIME%copilot_backend" --host 127.0.0.1 --port %PANEL_PORT%
