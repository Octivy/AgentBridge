# AgentBridge 1.0.0-alpha.1 发布说明

日期：2026-08-12

## 亮点

- 产品级桌面应用（WPF + WebView2）：主窗口 / 侧边导航 / 托盘 / 后端托管 / 自动拉起软件桥。
- 配置中心：软件（Host 适配器）配置 CRUD、启停、测试、状态；持久化于 `%LOCALAPPDATA%\AgentBridge`。
- MCP 接入管理：一键生成并写入 `~/.codex/config.toml` 与 `.mcp.json`（合并保留原配置）。
- 控制面 MCP（`agentbridge`，16 个工具）：Agent 可自查软件、管理桥、注册 MCP、生成适配器脚手架、登记交付。
- Agent 任务执行（`/agent/task`、`ab_run_task`）：需求拆解 → 宿主工具执行（hosts/cadmcp/all）→
  写工具 dry-run 自动批准 → 自动写交接总结；真实 DeepSeek 驱动 Blender 完成“建模 + 渲染 + 总结 + 回滚”实机演示。
- 任务交付：交付物（文件/截图/报告/模型）+ 交接总结，UI 与 API 均可查询。
- 适配器：Blender（6 工具，实机验证）、SketchUp（2 工具，SketchUp 2025 实机验证通过）、
  Rhino（Python，契约测试通过，待 Rhino 重装后实机）、AutoCAD cadmcp（13 工具）。
- 一键安装：客户端一键装 SketchUp 扩展 / Blender 插件，打开软件即自动连接
  （Blender 已在可见 GUI 窗口实测生成别墅模型）。

## 质量

- pytest 215 通过 + 4 子测试；ruff 全绿；桌面端 Release 构建通过；便携包可产出。

## 验收与发布

详见 [docs/acceptance-checklist-2026-08-12.md](acceptance-checklist-2026-08-12.md)。
SketchUp / Rhino 实机最终验收见同文件；验收完成后可从 alpha 转正式版本。
