# AgentBridge Host Adapter Contract v1

日期：2026-08-12
状态：v1 基线，随实现修订

## 1. 目的

让任意目标软件（AutoCAD、Blender、SketchUp、Rhino……）以最小的“宿主适配器”暴露给 AgentBridge 客户端，使 Codex/Claude 等外部 Agent 通过客户端统一操作这些软件。客户端不实现任何软件业务功能，只做：宿主发现、工具注册、权限批准、Agent 接入和诊断。

这与现有 AutoCAD 本地桥（`127.0.0.1:8765`、`x-cadcopilot-token`、协议 2.0）同源：本契约把该模式标准化并推广到多软件。

## 2. 传输与安全

- 传输：HTTP/1.1，JSON 请求/响应；适配器只绑定 `127.0.0.1`（默认），与客户端同机。
- 认证：请求头 `x-cadcopilot-token`。适配器启动时自生成随机 token，通过注册文件交给客户端。缺失/错误 → `401 {"ok": false, "error_code": "unauthorized"}`。
- 协议版本：`1.0`（在 `/manifest` 中声明；客户端兼容 1.x）。
- 写安全：写工具（`side_effect_level != "none"`）必须支持 `dry_run`；非 dry-run 调用必须携带 `arguments.permission_request_id`（由客户端人工批准后注入）。适配器只校验存在性，与现有 AutoCAD 桥行为一致；HMAC 票据的签发与校验在客户端/MCP 层完成（沿用 `cadmcp.permission_ticket`）。

## 3. 注册（Discovery）

适配器启动时原子写入注册文件，退出时清理（尽力而为）：

```text
%LOCALAPPDATA%\AgentBridge\hosts\<host_id>-<pid>.json
```

```json
{
  "schema_version": 1,
  "host_id": "blender-main",
  "host_kind": "blender",
  "product": "Blender",
  "product_version": "4.2.0",
  "protocol_version": "1.0",
  "endpoint": "http://127.0.0.1:8870",
  "token": "random-64-hex",
  "pid": 12345,
  "registered_at": "2026-08-12T10:00:00+08:00"
}
```

客户端轮询注册目录（默认 5 秒），读取后调用 `/health` 校验 token 与存活状态。注册文件仅当前用户可读。

## 4. 端点

| 方法 | 路径 | 请求 | 成功响应 |
| --- | --- | --- | --- |
| GET | `/manifest` | - | 工具清单与能力声明 |
| GET | `/health` | - | 软件运行状态 |
| POST | `/snapshot` | `{"scope": {...}}` | 结构化快照 |
| POST | `/tools/<tool_name>` | `{"arguments": {...}, "dry_run": bool, "trace_id": ""}` | 工具执行结果 |
| POST | `/rollback` | `{"rollback_token": "..."}` | 撤销结果 |

统一错误响应：`{"ok": false, "error_code": "...", "error_message": "..."}`。

### 4.1 /manifest

```json
{
  "schema_version": 1,
  "host_id": "blender-main",
  "host_kind": "blender",
  "product": "Blender",
  "product_version": "4.2.0",
  "protocol_version": "1.0",
  "capabilities": ["snapshot", "dry_run", "rollback"],
  "tools": [
    {
      "tool_name": "blender_scene_summary",
      "display_name": "场景摘要",
      "category": "analysis",
      "description": "汇总当前 Blender 场景的对象、集合与渲染设置。",
      "input_schema": {"type": "object", "properties": {}, "additionalProperties": false},
      "dry_run_supported": false,
      "side_effect_level": "none",
      "result_schema": {"type": "object"}
    }
  ]
}
```

工具定义与 `cadmcp.tool_registry.ToolDefinition` 对齐，保证客户端工具白名单、MCP 工具列表和权限策略共用同一份 Schema。

### 4.2 /health

```json
{"ok": true, "product": "Blender", "product_version": "4.2.0", "document_open": true, "detail": {"scene": "Scene"}}
```

### 4.3 /snapshot

返回软件自身的结构化快照；字段由各软件定义，但必须包含 `schema_version` 与 `source`。

### 4.4 /tools/<tool_name>

```json
// 请求
{"arguments": {"size": 1.0}, "dry_run": true, "trace_id": "tr_123"}
// 响应（读工具 / dry-run）
{"ok": true, "result": {"preview": {...}}, "dry_run": true}
// 响应（已授权写工具）
{"ok": true, "result": {"object_id": "Cube.001"}, "dry_run": false, "rollback_token": "rb_abc"}
```

写工具在非 dry-run 时必须校验 `arguments.permission_request_id`；缺失 → `403 {"ok": false, "error_code": "permission_required"}`。支持撤销的工具返回 `rollback_token`。

### 4.5 /rollback

```json
{"ok": true, "result": {"rolled_back": true}}
```

## 5. 适配器最小实现清单

1. `/manifest` 至少暴露 1 个工具，工具 Schema 完整。
2. `/health` 反映软件真实运行状态。
3. `/snapshot` 返回结构化快照（可为空摘要，但不能失败）。
4. 写工具支持 `dry_run`，非 dry-run 校验 `permission_request_id`。
5. 启动时写注册文件，退出时清理。
6. 只监听回环地址；token 不得为空。

## 6. 客户端职责

- 轮询注册目录，维护可用宿主列表与能力合并视图。
- 对 Agent 暴露统一 MCP 工具面（`<host_kind>_<tool_name>` 命名空间）。
- 写操作：先 dry-run → 人工批准 → 签发一次性权限票据 → 携带 `permission_request_id` 调用适配器。
- 记录 trace id、工具执行事件与诊断。

多宿主 MCP 工具面由 `copilot_backend/host_mcp` 实现（FastMCP 服务，默认 `stdio`，可选 `streamable-http`/`sse`，端口 `8767`）：

```powershell
python -m host_mcp --transport stdio --registry-dir "$env:LOCALAPPDATA\AgentBridge\hosts"
```

仓库内可直接使用启动脚本（自动定位 Python 与注册目录）：

```powershell
.\scripts\start-hostmcp.ps1 -Transport stdio
```

工具执行遵循与 `cadmcp` 相同的票据模型：写工具 dry-run 返回 `permission_token`/`preview_hash`/`permission_request_id`，非 dry-run 必须携带票据且一次性有效；`evaluate_commit_policy` 对破坏性写强制 `confirmed_by_local_user`。

后端 `GET /hosts` 返回当前发现的宿主、工具清单和发现错误；`GET /ui` 提供独立客户端面板（宿主状态、工具清单、对话），供浏览器或后续桌面外壳使用。`hostmcp` 已注册到项目级 `.codex/config.toml` 与 `.mcp.json`（Codex/Claude Code 可直接接入）。

## 7. 各软件接入方式（参考）

| 软件 | 适配器形态 | 说明 |
| --- | --- | --- |
| AutoCAD | C# 插件（已实现） | 本地桥已实现 `/manifest`、`/snapshot`、`/tools/<name>`、`/rollback`，以 `autocad-main` 注册 |
| Blender | Python add-on | `bpy` 事件循环内起 HTTP 线程，本仓库已提供骨架 |
| SketchUp | Ruby 扩展 | `TCPServer` 起本地服务（已提供骨架） |
| Rhino | C# 插件或 Rhino.Python | 起本地 HTTP 服务，依赖 Rhino 8 内置 Python |

## 8. 版本演进

- v1.0：单机回环 + 注册文件发现 + dry-run/授权/撤销。
- v1.1（规划）：WebSocket 事件推送（软件内选择集变化、任务进度）、Streamable HTTP MCP 传输。
- v2.0（规划）：远程宿主（TLS + 登录）、多用户会话。
