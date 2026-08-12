# CADMCP

`cadmcp` 是从 `copilot_backend` 中拆出的独立 CAD 工具协议层。它负责 MCP 工具发现、输入 schema、风险元数据、统一结果协议、AutoCAD 本地桥接和 stdio/HTTP transport；模型调用与 Planner 仍属于 `copilot_backend`。

## 运行

在仓库根目录：

```powershell
.\scripts\start-cadmcp.ps1
```

或直接运行：

```powershell
.\.venv\Scripts\python.exe -m cadmcp --transport stdio
```

Streamable HTTP：

```powershell
.\.venv\Scripts\python.exe -m cadmcp --transport streamable-http --host 127.0.0.1 --port 8766
```

环境变量：

- `CADMCP_BRIDGE_URL`：AutoCAD 插件内本地桥地址，默认 `http://127.0.0.1:8765`。
- `CADMCP_BRIDGE_TOKEN`：本地桥共享令牌；正式环境应配置非空值。
- `CADMCP_BRIDGE_TIMEOUT_SECONDS`：桥接调用超时，默认 30 秒。
- `CADMCP_HOST` / `CADMCP_PORT` / `CADMCP_TRANSPORT`：MCP transport 配置。

旧的 `copilot_backend/mcp_runtime/*` 和 `copilot_backend/mcp_server.py` 是兼容入口，新代码应直接导入 `cadmcp`。

## 安全约定

所有写工具的 MCP schema 都包含 `dry_run`，且省略时按 `true` 处理。Host 应先审阅预览，再经用户确认以 `dry_run=false` 应用。Codex 项目配置还将服务级审批模式设为 `writes`。

## Codex

仓库已提供 `.codex/config.toml`。把项目标记为 trusted 后，Codex CLI、桌面应用和 IDE 扩展会发现名为 `cadmcp` 的项目级 MCP server。新任务启动后可运行：

```powershell
codex mcp list
```

确认 `cadmcp` 为 `enabled`。AutoCAD 插件必须已加载且本地桥健康，实际工具调用才会成功。

## 第一阶段产品工具面

默认 MCP Server 只暴露 CAD/天正 AI 连接 MVP 所需的 13 个工具：

- 连接/读取：`cad_health_check`、`get_drawing_snapshot`、`list_layers`、`arch_get_drawing_context`
- 识别：`arch_recognize_functional_objects`、`arch_extract_outer_outline`、`arch_suggest_layer_mapping`
- 最小写入：`ensure_layer`、`draw_line`、`execute_draw_batch`、`arch_draw_outer_outline`、`arch_apply_layer_mapping`
- 安全：`cad_rollback_transaction`，以及每个写工具内置的 dry-run/permission contract

墙、门、窗创作以及单线/双线围合空间工具不在当前代码注册表和产品入口中；相关历史实现已移到项目上一级备份区。围合空间属于连接器和真实 DWG 验证通过后的第二阶段能力。

推荐验证顺序：健康检查 → 图纸快照 → 功能对象识别 → 外围轮廓提取/预演/提交/回滚 → 图层映射建议/预演/提交/回滚。真实 DWG 验证方法见 `docs/real-dwg-validation-matrix-2026-07-18.md`。
