# MCP 架构与接入

更新日期：2026-07-24

## 主链路

```text
Codex / 其他 MCP Host
        │ stdio MCP
        ▼
cadmcp (Python, 13 个产品工具)
        │ HTTP + 本地 token
        ▼
LocalToolBridge (AutoCAD 2024 插件进程)
        │ AutoCAD 主线程
        ▼
SnapshotExtractor / CommandExecutor
```

`copilot_backend` 提供 Planner、模型 provider 和 HTTP UI 服务；它复用 `cadmcp`，不维护第二份工具实现。`copilot_backend/mcp_runtime` 与 `mcp_server.py` 只保留兼容导入/启动入口。

## 工具边界

读取工具：`cad_health_check`、`get_drawing_snapshot`、`list_layers`、`arch_get_drawing_context`、`arch_recognize_functional_objects`、`arch_extract_outer_outline`、`arch_suggest_layer_mapping`。

写入工具：`ensure_layer`、`draw_line`、`execute_draw_batch`、`arch_draw_outer_outline`、`arch_apply_layer_mapping`、`cad_rollback_transaction`。

墙、门、窗、房间、轴网、楼梯、标注等独立创编工具不属于当前 MCP 产品契约。

## 写入安全契约

1. Host 必须先以 `dry_run=true` 请求预览。
2. `cadmcp` 返回绑定工具名和业务参数的一次性权限票据。
3. 用户确认后，Host 携带 `permission_token` 与 `preview_hash` 提交。
4. Python 执行层消费票据，并向本地桥传递 `permission_request_id`。
5. C# 本地桥拒绝没有授权请求 ID 的真实写入。
6. `CommandExecutor` 在 AutoCAD 原子事务内提交并复验 Handle。
7. 支持回滚的结果返回 `rollback_token`；提交后实体被人工修改时，回滚会拒绝覆盖较新的工作。

## 启动

1. 在 AutoCAD 2024 中加载插件，确认日志出现 `LocalToolBridge listening`。
2. 运行 `.\scripts\start-cadmcp.ps1`。
3. Codex 使用仓库 `.codex/config.toml`；其他 Host 注册同一脚本。
4. 正式环境配置非空且一致的桥接 token。

插件设置页的“连接诊断”读取 backend `/connector/diagnostics`，一次返回 backend、模型网关、CADMCP、本地桥、AutoCAD 五层状态与恢复建议；`/health` 只承担轻量存活检查。诊断不依赖用户会话、商业套餐或发布清单。

Claude Desktop 等 Host 的示例：

```json
{
  "mcpServers": {
    "cadmcp": {
      "command": "powershell.exe",
      "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "E:/AgentBridge/AgentBridge/scripts/start-cadmcp.ps1"],
      "env": {
        "CADMCP_BRIDGE_URL": "http://127.0.0.1:8765",
        "CADMCP_BRIDGE_TOKEN": "<与插件配置一致>"
      }
    }
  }
}
```

## 验证

- `scripts/test_mcp_stdio_handshake.py`：检查 MCP 初始化与工具白名单。
- `scripts/validate_mvp_snapshot.py`：不启动 AutoCAD 的算法回归。
- `copilot_backend/tests/`：权限、Planner、provider、工具和 HTTP 契约回归。
- AutoCAD 内真实提交：验证图形位置、图层、Handle、事务和回滚。
