# 开发环境快速检查与启动

更新时间：2026-07-21

本清单只覆盖当前 AutoCAD 2024 + `cadmcp` 连接器基座。产品范围和阶段门槛以 [产品定义 v5.2](product-prd-v5-semantic-conversion.md) 与 [当前工作计划](work-plan.md) 为准。

## 1. 环境前提

- Windows + AutoCAD 2024。
- .NET SDK 可执行 `dotnet`，目标为 .NET Framework 4.8。
- Python 3.10+；推荐使用 `copilot_backend/.venv`。
- AutoCAD 2024 引用目录可由项目属性或 `AutoCADInstallDir` 指定。
- 本地密钥只放在 `copilot_backend/.env` 或未跟踪的 `agentbridge.config.json`。

## 2. 一键恢复与启动

```powershell
.\start-local-dev.ps1
```

仅恢复、构建和安装插件：

```powershell
.\restore-local-dev.ps1
```

仅安装已有 bundle：

```powershell
.\install.ps1
```

## 3. 分组件启动

Backend：

```powershell
.\copilot_backend\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

检查 backend：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

MCP stdio：

```powershell
.\scripts\start-cadmcp.ps1
```

Codex 使用项目 `.codex/config.toml`；其他 Host 注册相同脚本，并保持 `CADMCP_BRIDGE_URL`、`CADMCP_BRIDGE_TOKEN` 与插件一致。

## 4. 自动验证

```powershell
dotnet build .\AgentBridge.sln -c Debug
.\AgentBridge.Tests\bin\Debug\net48\AgentBridge.Tests.exe
.\.venv\Scripts\python.exe -m unittest discover -s .\copilot_backend\tests -p "test_*.py"
.\copilot_backend\.venv\Scripts\python.exe .\scripts\validate_mvp_snapshot.py .\scripts\fixtures\mvp-rectangle-snapshot.json --expected .\scripts\fixtures\mvp-rectangle-expected.json
.\copilot_backend\.venv\Scripts\python.exe .\scripts\test_mcp_stdio_handshake.py
```

预期：C# 0 警告、0 错误；Python 测试全绿；MCP 只暴露 13 个产品工具。

## 5. AutoCAD 2024 冒烟

1. 加载插件，执行 `TestCopilot`，确认插件和本地桥已启动。
2. 执行 `AICHAT`，打开设置中的“连接诊断”，确认 `/connector/diagnostics` 返回五层状态。
3. 执行 `AISNAPSHOT`，确认能够导出当前图纸快照。
4. 从 Codex 调用 `cad_health_check`、`list_layers`、`get_drawing_snapshot`。
5. 连接器阶段不要用“画矩形房间”等已移除的类天正工具作为冒烟标准。

## 6. 常见分层故障

- Host 看不到 `cadmcp`：检查项目 trust、`.codex/config.toml` 或 Host MCP 配置。
- MCP 已启动但无法读 CAD：检查 AutoCAD 插件、本地桥端口和 token。
- 插件诊断失败：先检查 `http://127.0.0.1:8000/health`。
- 模型请求失败：区分无效 Key、模型名、协议、限流、超时和 provider 返回格式。
- 写入失败：确认已经 dry-run、获得一次性权限票据，并在 AutoCAD 本地确认。

## 7. 跨机器

交接使用 `prepare-handoff.ps1`，不要复制 `.venv`、`bin/`、`obj/`、`.env` 或本机配置。详细流程见 [cross-machine-workflow.md](cross-machine-workflow.md)。
