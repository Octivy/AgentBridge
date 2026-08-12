# AgentBridge 桌面客户端 PRD（方案 B）

- 版本：1.0.0-alpha.1
- 日期：2026-08-12
- 状态：已实现核心闭环，进入验收与发布阶段

## 1. 产品概述

AgentBridge 是一个**产品级桌面应用**，充当 AI Agent（Codex / Claude / 其他 MCP 客户端）与本机
专业软件（AutoCAD、Blender、SketchUp、Rhino …）之间的桥：

- 搭好连接：在客户端里配置/一键安装各软件的适配器（Host Adapter）；
- 监测运行：宿主在线状态、健康、工具清单、日志；
- 帮没有 MCP 的软件建立桥接：为任意软件生成 Host Adapter 脚手架；
- 自我接入 Agent：配置中心自己作为 MCP 服务器（`agentbridge`）接入 Codex 等，让 Agent
  能自查软件、管理桥、写 MCP 配置、生成适配器；
- 让 Agent 干活：一句话需求 → Agent 拆解 → 调用软件工具（写操作安全授权）→ 产出交付物 →
  自动写交接总结。

产品形态：**桌面客户端为主**（WPF + 内嵌 WebView2 面板），浏览器访问 `http://127.0.0.1:8000/ui`
仅用于开发/调试，正式用户入口是 `AgentBridge.Desktop.exe`。

## 2. 目标用户与核心场景

目标用户：需要让 AI 直接操作专业软件的设计/工程人员（建筑、室内、产品、BIM、CAD 用户）。

核心场景：

- 场景 A（接入）：用户装好客户端，在“软件配置”页一键安装 SketchUp 扩展 / 配置 Blender、
  Rhino、AutoCAD，重启软件即完成连接。
- 场景 B（让 Codex 控制软件）：在客户端“Agent 接入”页一键写入 Codex 配置；重启 Codex 后
  新会话即可原生调用 `cadmcp_*` / `hostmcp_*` / `ab_*` 工具。
- 场景 C（复杂任务与交付）：用户说“在 Blender 里建一个球并渲染截图”，Agent 自动拆解执行，
  完成后在“任务交付”页查看交付物与交接总结。

## 3. 功能需求

### FR1 桌面客户端壳

- 主窗口 + 左侧导航（总览 / 软件配置 / 连接监控 / Agent 接入 / 任务交付）；
- 内容区为内嵌 WebView2 配置中心面板；
- 托盘：最小化到托盘、显示主窗口、重启后端、退出；
- 后端进程托管：自动定位仓库与 Python、启动 uvicorn、健康检查、崩溃自动重启；
- 状态栏：后端版本与运行状态。

### FR2 软件配置中心

- 软件（Host 适配器）卡片：名称、类型、在线/离线/已注册/未启用状态、版本、端点；
- 新增/编辑/删除软件桥；启动/停止其 MCP 进程；测试连接；
- 一键安装适配器：SketchUp 扩展自动探测版本并装入 Extensions 目录（重启生效）；
- 配置持久化：`%LOCALAPPDATA%\AgentBridge\host_configs.json`。

### FR3 连接监控

- 已注册宿主列表（Host Adapter Contract v1：/manifest /health）；
- 工具清单、注册错误；支持按宿主查看健康与端点。

### FR4 MCP 接入管理

- 一键生成并写入 `~/.codex/config.toml`（合并保留原配置，注册 agentbridge/cadmcp/hostmcp）；
- 一键写入项目 `.mcp.json`（Claude 等，自动备份旧文件）；
- 查看 Codex 已注册 vs 可生成的服务。

### FR5 控制面 MCP（`agentbridge`，16 个工具）

- 软件管理：`ab_list_software` / `ab_software_status` / `ab_test_connection` /
  `ab_add_host` / `ab_update_host` / `ab_remove_host` / `ab_start_host` / `ab_stop_host`；
- 接入：`ab_preview_mcp` / `ab_register_with_codex` / `ab_register_with_claude`；
- 自搭桥：`ab_scaffold_adapter`（生成可运行的 Host Adapter 脚手架）；
- 交付：`ab_list_deliveries` / `ab_record_deliverable` / `ab_set_handoff`；
- 任务：`ab_run_task`（需求 → 拆解 → 执行 → 交付）。

### FR6 Agent 任务执行

- `POST /agent/task` 与 `ab_run_task`；
- 工具范围：hosts / cadmcp / all；
- 批准模式：full（写工具 dry-run 自动批准）/ execute / annotate（需确认）；
- 流程：AgentLoop → 宿主工具执行 → 自动写交接总结 → 交付记录；
- 已实机验证：DeepSeek 驱动 Blender 完成“建球 → 渲染 PNG → 总结 → 回滚”。

### FR7 任务交付

- 交付物（文件/截图/报告/模型）+ 交接总结（做了什么/如何验证/下一步）；
- API `/delivery/*` + UI“任务交付”页（运行任务表单 + 交付列表 + 登记表单）。

### FR8 多软件适配器

- Blender：6 工具（摘要/几何体/移动/程序化别墅/渲染），实机验证通过；
- SketchUp：2 工具（摘要/创建长方体），正式扩展 + 一键安装，实机验证通过；
- Rhino：Python 适配器（摘要/长方体），契约测试通过，待 Rhino 重装后实机；
- AutoCAD：cadmcp 13 个白名单工具，写操作事务/回滚。

## 4. 用户旅程（如何使用）

1. 安装：运行 `dist\AgentBridge\setup-backend.ps1`（首次初始化后端环境），然后
   `app\AgentBridge.Desktop.exe`（或 `install-desktop.ps1` 装到开始菜单，可 `-AutoStart`）。
2. 连接软件：
   - SketchUp：软件配置 → SketchUp 卡片 → “一键安装 SketchUp 扩展” → 重启 SketchUp；
   - Blender：在 Blender 中运行后台宿主（或按适配器 README 配置），重启后自动注册；
   - Rhino / AutoCAD：同款卡片配置/一键安装（Rhino 待重装后补齐一键安装）。
3. 查看连接：连接监控页确认宿主在线、工具就绪。
4. 接入 Codex：Agent 接入页 → “写入 Codex 配置（~/.codex/config.toml）” → 重启 Codex →
   新开会话即可原生使用全部工具（`cadmcp_*`/`hostmcp_*`/`ab_*`）。
5. 干活与交付：任务交付页直接“运行 Agent 任务”，或在 Codex 里对 `ab_run_task` 说需求；
   完成后交付物与交接总结自动登记，可在同一页查看。

## 5. 非功能需求

- 安全：宿主回环绑定 + token 鉴权；写操作 dry-run → 一次性授权 → 事务 → Handle 校验 → 回滚；
  破坏性写需本地确认。
- 兼容：Windows x64；.NET 8；Python 3.11；SketchUp 2021/2022/2025、Blender 5.x、Rhino 8、AutoCAD 2024。
- 质量：pytest 212 + 子测试通过；ruff 全绿；桌面端 Release 构建通过；便携包可产出。
- 可用性：一键安装/一键接入，尽量减少手工配置；无后台线程依赖（SketchUp 用主线程定时器服务）。

## 6. 边界与后续规划

- Rhino 重装后：一键安装适配器 + 实机验收；
- SketchUp 扩展后续：随客户端版本同步更新 rbz 版本号；
- 安装器：MSIX / Inno Setup 完整安装包（当前为便携包 + 安装脚本）；
- CI/发布：tag 自动建 prerelease（已接入）；正式版 1.0.0 前完成 Rhino 验收与打包打磨。

## 7. 验收标准

见 [acceptance-checklist-2026-08-12.md](acceptance-checklist-2026-08-12.md)；
功能/交互与本 PRD 逐条对应，验收通过后由 alpha 转正式版本。
