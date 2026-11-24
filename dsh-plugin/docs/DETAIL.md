# AgentBridge 桥接

把本机 CAD/建模软件接入 DeepSeek Harness 的中间调和层：连接、解释、权限票据与回滚。智能决策归 Agent，几何执行归软件，AgentBridge 只做桥梁。

## 它注册了什么

安装并启用后，DeepSeek Harness 通过官方 MCP 客户端接入三个 AgentBridge 服务器，Agent 获得约 52 个工具：

| 服务器 | 工具 | 作用 |
|---|---|---|
| `mcp__hostmcp__*` | 22 | `<软件>_<工具>` 命名空间，直接读写 AutoCAD / Rhino / SketchUp / Blender |
| `mcp__cadmcp__*` | 13 | AutoCAD 制图工具（画线、批量绘图等） |
| `mcp__agentbridge__*` | 19 | `ab_*` 控制平面 + 解释层 + 一键装适配器（`ab_install_adapter`、`ab_adapter_status`、`ab_explain_drawing` 等） |

工具名示例：`mcp__hostmcp__autocad_get_drawing_snapshot`、`mcp__agentbridge__ab_explain_drawing`。

## 前置条件

**无需额外安装。** 插件内置 Python 3.11 运行时 + 全部后端代码与软件适配器，
装上即可用（首次连接会随内置解释器自动加载依赖，约几秒）。

## 使用方式

1. 安装本插件并启用（插件管理器 → 已安装 → AgentBridge 桥接）；
2. 在 Agent 对话中直接让 Agent 读图/建模，例如："读取 AutoCAD 当前图纸并解释它"、
   "在 Rhino 里按平面图墙体生成 3D 模型"；
3. 写操作由工具协议保证：`dry_run` 预览 → `permission_token`/`preview_hash` 提交 → `rollback_token` 回滚。

## 连接不上的排查

- 软件未打开 / 适配器未装：先打开软件，再让 Agent 用 `mcp__agentbridge__ab_list_software` 查看状态；
- 适配器未装：让 Agent 调 `mcp__agentbridge__ab_install_adapter(host_kind="blender|sketchup|rhino|autocad")` 一键安装，重启软件即自动连接；
- 首次连接慢：三个服务器首次启动要 import 依赖，`startupTimeoutMs` 已放宽到 30 秒；
- 详细工作流见 `docs/SKILL.md`。

## 说明与限制

- 四个软件（AutoCAD / Rhino / SketchUp / Blender）的适配器都可用 `ab_install_adapter` 一键安装
  （AutoCAD 为预编译 .NET bundle、Rhino 为脚本包、SketchUp 为扩展、Blender 为插件），重启软件即自动加载。
- 插件内置 Python 3.11 运行时 + 全部后端代码与适配器，无需额外安装。
