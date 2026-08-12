# Windows 安装与联调

说明补充：当前默认的开发与启动说明请优先看 [development-guide.md](development-guide.md) 和 [daily-dev-sop.md](daily-dev-sop.md)。

## 目标

这份文档说明如何在 Windows + AutoCAD 上安装 AgentBridge 插件，并连接本地 MiniMax 转接服务完成端到端验证。

## 1. 编译插件

在 Windows 机器上打开解决方案并编译：

```powershell
msbuild AgentBridge.sln /t:Build /p:Configuration=Release /p:Platform=x64
```

要求：

- 已安装 AutoCAD 2024 或相近版本
- `AutoCADInstallDir` 可解析到 `acmgd.dll`、`acdbmgd.dll`、`accoremgd.dll`、`AcWindows.dll`

## 2. 安装成 AutoCAD Bundle

在 PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

脚本会把插件拷贝到：

```text
%APPDATA%\Autodesk\ApplicationPlugins\AgentBridge.bundle
```

AutoCAD 重启后会自动加载该插件。

## 3. 配置插件

编辑文件：

```text
%APPDATA%\Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\agentbridge.config.json
```

默认推荐配置：

```json
{
  "CADCOPILOT_CONNECTION_MODE": "standard",
  "LLM_PROVIDER": "claude",
  "CLAUDE_API_KEY": "",
  "CLAUDE_MODEL": "claude-sonnet-4-20250514",
  "OPENAI_API_KEY": "",
  "OPENAI_API_BASE_URL": "https://api.openai.com/v1",
  "OPENAI_MODEL": "gpt-5.5",
  "CADCOPILOT_MODEL": "MiniMax-M2.7",
  "CADCOPILOT_API_BASE_URL": "http://127.0.0.1:8000",
  "LOG_LEVEL": "INFO"
}
```

说明：当前默认启动为标准模式；如果要切到智能体模式，可在聊天面板左下角按钮切换，或者把 `CADCOPILOT_CONNECTION_MODE` 设为 `service`。智能体模式下重点字段仍然是 `CADCOPILOT_API_BASE_URL`。右上角模型设置会分别记住标准模式模型和智能体模型，且可用“测试”按钮验证当前模型配置是否可用。

如果要启用 MCP 工具桥，建议补充：

```json
{
  "LOCAL_BRIDGE_ENABLED": "true",
  "LOCAL_BRIDGE_HOST": "127.0.0.1",
  "LOCAL_BRIDGE_PORT": "8765",
  "LOCAL_BRIDGE_TOKEN": ""
}
```

说明：插件加载后会自动启动本地工具桥，默认仅绑定本机回环地址。

如果要改成 OpenAI / GPT 的标准模式直连，可把配置改为：

```json
{
  "CADCOPILOT_CONNECTION_MODE": "standard",
  "LLM_PROVIDER": "openai",
  "OPENAI_API_KEY": "<your-openai-key>",
  "OPENAI_API_BASE_URL": "https://api.openai.com/v1",
  "OPENAI_MODEL": "gpt-5.5",
  "CADCOPILOT_API_BASE_URL": "http://127.0.0.1:8000",
  "LOG_LEVEL": "INFO"
}
```

或者直接在聊天面板右上角设置中切换为 `直连大模型 API`，再选择 `OpenAI / GPT` 并填写 API Key。

补充：MiniMax 密钥应只保存在本地忽略文件 `copilot_backend/.env` 中，不要写入受 Git 跟踪的文档或配置模板。

## 4. 启动 copilot backend

如果在 Windows 本机启动：

```powershell
cd copilot_backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
.env.example 复制为 .env，并在 .env 中填写 MINIMAX_API_KEY
uvicorn app:app --host 127.0.0.1 --port 8000
```

也可以在另一台机器启动，然后把 `CADCOPILOT_API_BASE_URL` 指向该机器地址。

先检查健康状态：

```powershell
curl http://127.0.0.1:8000/health
```

如果需要在家里和单位两端快速恢复开发，可直接参考 [startup-checklist.md](startup-checklist.md)。

## 5. AutoCAD 验证步骤

1. 启动 AutoCAD。
2. 输入 `AICHAT` 打开聊天面板。
3. 输入 `画一个 6000 x 4000 的矩形房间`。
4. 观察插件 UI 回复和图纸绘制结果。
5. 输入 `AISNAPSHOT` 验证图纸摘要能力。

## 5.1 MCP 验证步骤

1. 保持 AutoCAD 与插件已启动。
2. 访问 `http://127.0.0.1:8765/health`，确认返回插件与图纸状态。
3. 在 `copilot_backend` 目录执行 `.\.venv\Scripts\python .\mcp_server.py`。
4. 先执行 `.\.venv\Scripts\python .\smoke_test_mcp.py`，默认用 `dry_run` 跑通前 3 个里程碑。
5. 将该命令注册到 Claude Desktop 的 `mcpServers`。
6. 先测试 `cad_health_check`、`list_layers` 和 `get_drawing_snapshot`。
7. 再测试 `draw_line`、`execute_draw_batch`、`arch_draw_outer_outline` 与 `arch_apply_layer_mapping`；必须先用 `dry_run=true`。

如果第 2 步失败，先不要直接改代码，优先在项目根目录执行：

```powershell
.\diagnose-local-bridge.ps1
```

脚本会统一输出：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8765/health`
- bundle 配置里的 `LOCAL_BRIDGE_*`
- `cadcopilot.log` 中的 `LocalToolBridge` 相关日志
- bundle DLL 与最新构建 DLL 的时间戳和大小是否一致

## 6. 常见问题

### 聊天面板提示网络错误

- 检查 `copilot_backend` 是否已启动。
- 检查 `CADCOPILOT_API_BASE_URL` 是否指向正确地址。
- 检查 Windows 防火墙是否阻止了 8000 端口。

### 插件没有自动加载

- 检查 `%APPDATA%\Autodesk\ApplicationPlugins\AgentBridge.bundle` 是否存在。
- 检查 `PackageContents.xml` 里的 `SeriesMin/SeriesMax` 是否匹配当前 AutoCAD 版本。
- 可先用 `NETLOAD` 手动加载 `AgentBridge.dll` 验证。

### 模型只回复文字，没有绘图

- 优先先测简单几何：矩形、直线、圆。
- 如果服务返回的不是 JSON，检查 `copilot_backend` 的 provider 配置和系统提示模板。

### MCP Host 能连上，但工具执行失败

- 先检查 `http://127.0.0.1:8765/health` 是否可访问。
- 如果 8765 不通，先运行 `./diagnose-local-bridge.ps1`，优先看日志里是否出现 `LocalToolBridge listening` 或 `Failed to start LocalToolBridge`。
- 检查插件配置中的 `LOCAL_BRIDGE_TOKEN` 与 `.env` / Claude Desktop 配置里的 `CADCOPILOT_LOCAL_BRIDGE_TOKEN` 是否一致。
- 如果 `draw_line` 等直接工具失败，优先检查插件本地工具桥日志，而不是模型配置。

### 上传截图后模型看不懂图片

- 当前默认接入的是 MiniMax OpenAI 兼容文本接口，该接口目前不支持图片输入。
- 聊天面板里的截图仍可保留，但需要用户在文字里补充尺寸、空间关系和关注对象。
- 如果要让图片真正参与理解，需要单独接入 MiniMax Token Plan 的 `understand_image` MCP 能力，或改接支持视觉输入的模型端点。
