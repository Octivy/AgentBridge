# AgentBridge 产品总览（方案 B 桌面应用）

日期：2026-08-12

## 一句话定位

AgentBridge 是一个独立的产品级桌面应用，充当 Codex 等 AI Agent 与本地软件
（AutoCAD、Blender、SketchUp、Rhino …）之间的桥：搭好连接、监测运行条件、
帮助没有 MCP 的软件建立桥接，并让配置中心自己接入 Agent，由 Agent 搭桥、
写 MCP 配置，最终让 Agent 控制软件完成复杂任务并交付成果。

## 架构

```text
Codex / Claude / 其他 Agent
        │  MCP（stdio）
        ▼
AgentBridge.Desktop（WPF + WebView2 桌面应用）
        │  启动/托管 backend，托盘 + 状态栏
        ▼
配置中心 backend（FastAPI :8000）
   ├─ 软件(Host)配置中心：CRUD/启停/测试/状态  /config/hosts
   ├─ MCP 接入管理：一键写 Codex/.mcp.json    /config/mcp/*
   ├─ 任务交付：交付物 + 交接总结             /delivery/*
   ├─ Agent 任务执行：需求拆解 -> 宿主工具执行 /agent/task（tool_scope: hosts|cadmcp|all）
   └─ 控制面 MCP（agentbridge）：16 个工具     python -m control_mcp
        │  Host Adapter Contract v1（127.0.0.1 + token）
        ▼
软件宿主：cadmcp（AutoCAD）· hostmcp（Blender/Rhino/SketchUp 聚合）
```

## 组件与状态

| 组件 | 位置 | 状态 |
| --- | --- | --- |
| 桌面应用壳 | `desktop/AgentBridge.Desktop` | 已实现：WPF+WebView2、后端托管、托盘、自动拉起软件桥；实机启动验证通过 |
| 配置中心 | `copilot_backend/host_config` + `http_api/ui.html` | 已实现：4 个软件默认配置、启停/测试/状态、UI 卡片与表单 |
| MCP 接入管理 | `copilot_backend/mcp_registry` | 已实现：生成并写入 `~/.codex/config.toml` 与 `.mcp.json`（合并保留原配置） |
| 控制面 MCP | `copilot_backend/control_mcp` | 已实现：15 个工具（软件管理、MCP 接入、适配器脚手架、任务交付），stdio 握手验证 |
| 任务交付 | `copilot_backend/delivery` | 已实现：交付物 + 交接总结 + 查询，UI 面板可用 |
| Agent 任务执行 | `copilot_backend/agent/host_task.py` | 已实现：AgentLoop + 宿主工具 + 写工具自动批准 + 自动写交接；`ab_run_task` / `POST /agent/task` |
| Blender 适配器 | `adapters/blender` | 已实现并实机验证：场景摘要/几何体/移动/程序化别墅/渲染 |
| Rhino 适配器 | `adapters/rhino` | 已实现：摘要/长方体（dry-run+回滚），契约测试通过，待 Rhino 实机验收 |
| SketchUp 适配器 | `adapters/sketchup` | 已实现并实机验证通过（SketchUp 2025） |
| AutoCAD | `cadmcp` | 13 个白名单工具，写操作事务/回滚 |

## 快速开始

开发模式：

```powershell
dotnet build .\desktop\AgentBridge.Desktop\AgentBridge.Desktop.csproj -c Debug
.\desktop\AgentBridge.Desktop\bin\Debug\net8.0-windows\AgentBridge.Desktop.exe
```

浏览器直接使用配置中心（需先起 backend）：

```powershell
cd copilot_backend; python -m uvicorn app:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/ui
```

> 注意：正式用户入口是桌面客户端（`AgentBridge.Desktop.exe`），面板内嵌其中；
> 浏览器访问 `:8000/ui` 仅用于开发与调试。完整产品说明见
> [PRD](prd-agentbridge-desktop-2026-08-12.md) 与 [验收清单](acceptance-checklist-2026-08-12.md)。

接入 Codex：配置中心“Agent 接入”页一键写入 `~/.codex/config.toml`（或直接调
`POST /config/mcp/codex`），重启 Codex 后新会话即可原生使用
`cadmcp_*` / `hostmcp_*` / `ab_*` 工具。

便携打包与安装：

```powershell
.\scripts\pack-desktop.ps1          # 产出 dist\AgentBridge
.\dist\AgentBridge\setup-backend.ps1  # 初始化后端环境
.\dist\AgentBridge\install-desktop.ps1 -AutoStart  # 安装 + 开始菜单 + 自启
```

## 验证摘要

- 后端测试：202 个 pytest + 4 子测试全部通过。
- 桌面应用：发布包实机启动，2 秒后端就绪，Blender 在线识别，干净退出。
- Blender 实机：几何体创建/移动/回滚、别墅 dry-run、渲染出图全部通过。
- 控制面 MCP：stdio 握手列出 16 工具并成功调用。
- SketchUp 实机验收：SketchUp 2025 宿主注册/健康、场景摘要、创建长方体（dry-run→应用→回滚）全部通过。
- Agent 任务实机验证：DeepSeek 自主调用 Blender（创建球体 -> 渲染 PNG -> 场景确认 -> 中文总结），
  写工具 dry-run 自动批准，完成后回滚清理；/agent/task 与 ab_run_task 均可触发。
- Codex 接入：`~/.codex/config.toml` 已注册 agentbridge/cadmcp/hostmcp，原配置完整保留。

## 待办

- Rhino 重装后做最终实机验收。
- 版本发布：整理提交、打版本（建议 1.0.0-alpha）、CI 接入。
