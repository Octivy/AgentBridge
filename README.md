# AgentBridge

AgentBridge 是 **AI 智能体与软件之间的桥接平台**：让 Codex、Claude 等 Agent 通过标准 MCP 安全地操作本机上的各类软件（AutoCAD、Blender、SketchUp、Rhino……），并为任意软件提供宿主适配器（Host Adapter）接入能力。

一句话：**我们不做软件功能，只做 Agent 与软件之间的桥。**

> 产品总览（桌面应用 / 配置中心 / Agent 任务执行 / 交付闭环）见
> [docs/product-overview-2026-08-12.md](docs/product-overview-2026-08-12.md)。

## 架构

```text
Agent (Codex / Claude / 任意 MCP 客户端)
        │  MCP (stdio / streamable-http)
        ▼
AgentBridge 客户端（托盘常驻 / Web 面板 /ui）
        │  Host Adapter Contract v1（127.0.0.1 + token + 权限票据）
        ▼
宿主适配器：AutoCAD 插件 · Blender add-on · SketchUp Ruby · Rhino ...
```

核心组件：

- `desktop/`：产品级桌面客户端（WPF + WebView2），自启 backend、侧边导航、托盘与状态栏。
- `copilot_backend/host_runtime`：宿主注册发现、manifest 校验、统一调用客户端。
- `copilot_backend/host_mcp`：多宿主 MCP 工具面（`<host>_<tool>`），写工具 dry-run → 一次性票据 → 提交 → 回滚。
- `copilot_backend/agent`：原生工具调用 Agent Loop（OpenAI / Claude / DeepSeek / Ollama 协议适配 + 故障切换）。
- `adapters/`：各软件宿主适配器（Blender / SketchUp / Rhino）。
- `cadmcp/`：AutoCAD 连接器（首个宿主），13 个白名单工具。

设计基线见 [Host Adapter Contract v1](docs/host-adapter-contract-v1-2026-08-12.md) 与 [重新设计 v1](docs/redesign-v1-2026-08-11.md)。

## 当前能力

- 快速连接：面板一键"连接"完成 检测本机软件 → 安装插件/适配器 → 拉起桥接 → 等待注册 → 健康检查 → 持久化（enabled + auto_start）；一次配置成功，多次可用，之后每次只需检查连接状态。
- 连接自愈可见化：`auto_start` 桥进程崩溃自动重启（带重启预算防风暴）、端口冲突归因、连接生命周期事件流，监控页实时呈现（`/config/connection/*`）。
- 本机软件自动探测：扫描注册表与常见安装位置，识别 Blender / SketchUp / Rhino / AutoCAD 及插件安装状态（`GET /config/detect`）。
- 模型配置进面板：设置页选择服务商、填 Key、静态校验 + 真实连通测试，保存即生效，无需编辑 .env（`/config/model/*`）。
- 首次运行向导：总览页四步引导（连接软件 → 配模型 → 接入 Agent → 跑第一个任务），完成后自动隐藏。
- 多模型：OpenAI、Anthropic/Claude、DeepSeek、MiniMax、OpenAI Compatible、Ollama、企业内网接口；Provider 故障切换（在线 → 本地兜底）。
- 多宿主：AutoCAD（13 工具）、Blender（6 工具实机验证）、SketchUp（实机验证）、Rhino（实机验证）；Host Adapter 契约标准化，任意软件可接入。
- Skill 增强：Agent 任务自动注入与当前可用工具匹配的已启用 Skill 操作规程（操作要点 + 起手动作），让智能体按已验收的方式操作软件。
- Agent 任务体验：一句话命令异步执行，面板实时渲染步骤时间线（思考 / 工具 ✓✗ / 被拦截的写）；annotate 模式下写操作停下弹确认卡，批准（dry-run → 票据 → 提交）继续执行、拒绝交回模型，其后每次写操作逐一确认。
- 交付物可消费：交付卡片直接打开 / 打开目录 / 图片预览 / 台账令牌回滚（单条或全部），交付闭环到"拿到手"。
- 安全：回环绑定 + token 认证、写操作 dry-run → 一次性权限票据 → 事务/回滚、破坏性写强制本地确认。
- 对话与任务：标准模式问答、Planner、待审核 Skill 草稿、公司规范知识问答（来源引用与拒答）。

P1 闭环（写确认 / 过程可视化 / 交付动作）实现细节与验证记录见 [docs/p1-closedloop-2026-08-14.md](docs/p1-closedloop-2026-08-14.md)。

## AutoCAD 连接器（首个宿主）

面向 AutoCAD 2024 / 天正图纸的 AI 连接与专业 Skill：

1. 图纸快照分析：读取图层、实体、块、文字、尺寸及未知代理对象。
2. 功能对象识别：将图层线、普通块、动态块、可读取对象统一识别为墙、门、窗或未知对象。
3. 外围轮廓转换：从闭合平面提取最外围轮廓、计算面积，并可绘制闭合多段线。
4. 图层统一：给出保守的图层映射建议，经确认后迁移实体图层。

MCP 只暴露 13 个产品工具：

- 读取：`cad_health_check`、`get_drawing_snapshot`、`list_layers`
- 基础写入：`ensure_layer`、`draw_line`、`execute_draw_batch`、`cad_rollback_transaction`
- 专业读取：`arch_get_drawing_context`、`arch_recognize_functional_objects`、`arch_extract_outer_outline`、`arch_suggest_layer_mapping`
- 专业写入：`arch_draw_outer_outline`、`arch_apply_layer_mapping`

所有写入遵守“预览 → 一次性授权 → AutoCAD 事务提交 → Handle 校验 → 可选回滚”。墙、门、窗的创建与编辑工具已移出本项目，围合空间深化能力留待真实图纸验证通过后进入第二阶段。

当前预览版已实现能力、阶段完成度、自动化结果和安装验收建议见 [0.9.0.622 发布状态](docs/release-status-2026-08-11.md)。

## AutoCAD 命令

- `AICHAT`：打开聊天与任务面板。
- `AISNAPSHOT`：导出当前图纸 L2 快照到 `%TEMP%\AgentBridge\snapshots\`。
- `TestCopilot`：确认插件与本地 MCP 桥已加载，不修改图纸。

## 目录

```text
AgentBridge/
├─ desktop/                  # 产品级桌面客户端（WPF + WebView2，net8.0-windows）
├─ adapters/                # 各软件宿主适配器（Blender/SketchUp/Rhino）
├─ Core/                    # AutoCAD 插件：配置、本地 MCP 桥、主线程调度
├─ Engine/                  # AutoCAD 插件：快照提取、事务和回滚
├─ LLM/                     # 插件与 backend 的数据契约和客户端
├─ Plugin/                  # AutoCAD 命令入口
├─ UI/                      # WPF 聊天与任务界面
├─ cadmcp/                  # AutoCAD 独立 MCP Server、工具注册和专业能力
│  └─ domain/architecture/  # 功能识别、外围轮廓、图层映射
├─ copilot_backend/         # 客户端核心：host_runtime、host_mcp、agent、Planner、HTTP
├─ AgentBridge.Tests/       # C# 产品边界契约测试
├─ scripts/                 # MCP 启动、验证和冒烟脚本
└─ docs/                    # 当前有效产品与开发文档
```

## 环境

- Windows x64；AutoCAD 2024（R24.3）/ 2016（R20.1）/ 2014（R19.1）可编译
- .NET Framework 4.8 与 .NET 8（客户端）
- Python 3.10+
- 目标软件安装目录包含对应 API 程序集

## 本地启动

一键恢复、构建、安装并启动 backend：

```powershell
.\start-local-dev.ps1
```

仅构建：

```powershell
dotnet build .\AgentBridge.sln -c Debug
```

启动 backend（Web 面板：`http://127.0.0.1:8000/ui`）：

```powershell
cd copilot_backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

启动多宿主 MCP Server（Codex/Claude 接入外部软件）：

```powershell
.\scripts\start-hostmcp.ps1
```

启动 AutoCAD MCP Server：

```powershell
.\scripts\start-cadmcp.ps1
```

项目级 Codex 配置位于 `.codex/config.toml`；其他 MCP Host 注册见 `.mcp.json`。

## 安装器（Inno Setup）

一键产出 `AgentBridge-Setup-<版本>.exe`：目标机器**无需预装 Python / .NET**（自包含
发布 + 内嵌 Python 运行时），装完即有开始菜单快捷方式与卸载器。

```powershell
# 1. 打包安装源并编译安装器（首次会下载 Inno Setup 依赖与 Python embeddable）
.\scripts\pack-desktop-installer.ps1 -CompileWithIscc -Version 1.0.0

# 2. 产物：dist\AgentBridge-Setup-1.0.0.exe

# 3. 自举验证：静默安装到临时目录 → 启动 → backend /health 就绪 → 静默卸载
.\scripts\test-installer-bootstrap.ps1 -Version 1.0.0
```

安装布局：`{安装目录}\app`（桌面端）、`{安装目录}\backend\copilot_backend`（后端）、
`backend\adapters`（宿主适配器）、`backend\scripts`（桥启动脚本）、
`backend\runtime`（内嵌 Python + 依赖 + cadmcp）。

### 更换后端端口（默认 8000）

当 8000 被其他程序占用（如本机 DeepSeek Harness），三种方式指定端口，优先级从高到低：

1. 环境变量：`$env:AGENTBRIDGE_PORT=8210` 后启动 `AgentBridge.Desktop.exe`；
2. 配置文件：新建 `%LOCALAPPDATA%\AgentBridge\client.json`，内容 `{"backend_port": 8210}`（持久生效）；
3. 都不设置时用默认 8000。

面板、交付、自愈等功能同源自动跟随新端口。**AutoCAD 插件**侧的
`CADCOPILOT_API_BASE_URL` 需与端口一致（插件设置界面或 `agentbridge.config.json` 中修改；
插件本地桥走独立的 8765 端口，不受影响）。

## 验证

```powershell
# 本机装有 AutoCAD 2016（D:\Program Files\Autodesk\AutoCAD 2016）时，
# 需显式指定版本；装了 2024 时可直接省略 -p:AutoCADVersion=2016
dotnet build .\AgentBridge.sln -c Release -p:AutoCADVersion=2016
.\AgentBridge.Tests\bin\Release\net48\AgentBridge.Tests.exe
python -m pytest copilot_backend/tests
python .\scripts\validate_mvp_snapshot.py .\scripts\fixtures\mvp-rectangle-snapshot.json --expected .\scripts\fixtures\mvp-rectangle-expected.json
python .\scripts\test_mcp_stdio_handshake.py
.\scripts\run-connector-acceptance.ps1
```

## 当前决策门

下一步不是扩展更多绘图工具，而是把连接器基座验证到可重复：

- Codex 与另一种 MCP Host 的初始化、工具发现和连续读取成功率；
- 插件、backend、MCP 和本地桥的分层健康检查与错误恢复；
- OpenAI 兼容与 Anthropic Messages 两类模型协议；
- Planner 白名单、写入审批、trace id、重试和恢复链路；
- 已完成任务到待审核 Skill 草稿的转换、持久化和工具白名单校验；
- 外部软件宿主（Blender 等）的实机验证与 Host Adapter 契约回归。

连接器门槛通过后再进行至少 10 张真实 DWG 验证；两道门槛均通过后，才进入双线墙、门窗开口和围合空间识别的第二阶段。

一键验收、Claude Code 批准、AutoCAD 现场验证和当前阻断项见 [连接器验收指南](docs/connector-acceptance-guide-2026-07-24.md)。
