# AgentBridge 客户端（托盘）

独立于 AutoCAD 的 Windows 托盘客户端：负责启动/守护 backend（FastAPI），托盘菜单提供“打开面板 / 重启 backend / 退出”，面板即 `http://127.0.0.1:8000/ui`（宿主状态、Agent 工具、对话）。

## 构建

```powershell
dotnet build .\client\AgentBridge.Client\AgentBridge.Client.csproj -c Release
```

产物：`client\AgentBridge.Client\bin\Release\net8.0-windows\AgentBridge.Client.exe`

## 运行

```powershell
.\client\AgentBridge.Client\bin\Release\net8.0-windows\AgentBridge.Client.exe
```

或显式指定仓库根目录：

```powershell
.\AgentBridge.Client.exe "H:\codex\archiaicopilot\AgentBridge"
```

客户端会自动寻找 Python（优先 `.venv`，其次系统 `python`），在 `copilot_backend` 目录启动 `uvicorn app:app`，每 5 秒健康检查，backend 异常退出时自动重启。日志在 `%LOCALAPPDATA%\AgentBridge\client.log`。

## 与 AutoCAD 的关系

客户端不依赖 AutoCAD：宿主发现、Agent 接入、对话都由 backend 完成。AutoCAD（或 Blender 等）只需要运行各自的 host 适配器并在注册目录登记。
