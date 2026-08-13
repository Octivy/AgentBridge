# AgentBridge 验收清单（2026-08-12）

对照产品目标逐项给出实现证据、验证状态与剩余项，供最终验收与发布使用。

## 目标

产品级桌面应用：作为 Codex 及其他 Agent 与本地软件（AutoCAD / Blender / SketchUp / Rhino …）
之间的桥——搭好连接、监测运行条件、帮助没有 MCP 的软件建立桥接；配置中心自己接入 Agent，
由 Agent 搭桥、写 MCP 配置；最终让 Agent 控制软件完成复杂任务并交付成果。

## 验收项与证据

| # | 验收项 | 证据 | 状态 |
| --- | --- | --- | --- |
| 1 | 独立桌面应用（WPF + WebView2） | `desktop/AgentBridge.Desktop`：主窗口/侧边导航/托盘/后端托管/自动拉起软件桥；发布包实机启动验证（后端 2 秒就绪、干净退出） | ✅ |
| 2 | 配置中心：配置各软件、启停、测试、状态、一键安装 | `copilot_backend/host_config` + `adapter_install` + `/config/hosts` API + UI；SketchUp 扩展 / Blender 插件一键安装实测 | ✅ |
| 3 | 监测运行条件 | `/config/hosts` 状态（注册/健康/进程）+ UI 连接监控页 + 桌面端健康轮询 | ✅ |
| 4 | 帮没有 MCP 的软件建立桥接 | 控制面 `ab_scaffold_adapter` 生成可运行 Host Adapter 脚手架（已测试：生成的 Rhino 适配器能响应 /manifest）；Rhino/SketchUp 适配器已落地 | ✅（脚手架/适配器）；SketchUp 实机 ✅；Rhino ✅ 实机（2026-08-13） |
| 5 | 配置中心自我接入 Agent | 控制面 MCP `agentbridge`（16 工具，stdio 握手验证）+ 一键写入 `~/.codex/config.toml` / `.mcp.json` | ✅ |
| 6 | Agent 搭桥、写 MCP 配置 | `ab_add_host/update/remove`、`ab_register_with_codex/claude`、`ab_scaffold_adapter`（测试 + 实机调用） | ✅ |
| 7 | Agent 控制软件完成复杂任务 | `/agent/task` + `ab_run_task`：真实 DeepSeek 实机完成“查场景→创建球体(dry-run+自动提交)→渲染 PNG→总结→回滚”，PNG 28KB 落盘 | ✅（Blender） |
| 8 | 交付成果 | `delivery` 模块 + `/delivery/*` + UI 任务交付页（交付物/交接总结），Agent 任务自动写交接 | ✅ |
| 9 | 多软件适配器 | Blender 实机验证（6 工具，含可见 GUI 窗口建别墅）；SketchUp 实机验证（2 工具，SketchUp 2025）；Rhino 8 实机验证（2 工具：场景摘要 / 创建长方体，含回滚，主线程执行架构）；AutoCAD cadmcp 13 工具 | ✅ |
| 10 | 质量门禁 | pytest 219 通过 + 4 子测试；ruff 全绿；桌面端 Release 构建通过；打包脚本可产出便携包 | ✅ |

## 发布前置

- [ ] 提交本轮全部改动（建议按适配器/配置中心/控制面与交付/Agent 任务/桌面与打包分步）
- [ ] 打版本 `1.0.0-alpha.1`（版本号统一：`docs/product-overview` + 打包产物）
- [x] SketchUp 2025 实机验收（宿主注册 + 健康 + 摘要 + 创建/回滚）
- [x] Blender 可见窗口实机（一键安装插件 + 自动连接 + 界面生成别墅模型）
- [x] Rhino 8 实机验收（宿主注册 + 工具调用 + 回滚，2026-08-13）
- [ ] 在真实 Codex 会话中用 `ab_run_task` 复跑一次复杂任务
- [ ] CI 全绿（现有 `ci.yml` 已覆盖 pytest/ruff/wheel，新增依赖 `tomli_w` 已入 requirements）
