# 产品技术架构

## 组件

| 组件 | 职责 |
| --- | --- |
| AutoCAD 2024 插件 | 图纸快照、主线程 CAD 操作、聊天 UI、本地桥 |
| `cadmcp` | MCP 协议、13 个工具、权限票据、语义能力 |
| `copilot_backend` | Planner、HTTP API、多模型适配、任务事件 |
| MCP Host | Codex 或其他支持 MCP 的模型客户端 |

## 数据流

读取链路：Host → `cadmcp` → 本地桥 → `SnapshotExtractor` → 结构化快照 → 功能识别/外围轮廓/图层建议。

写入链路：Host → dry-run → 用户授权 → `cadmcp` 消费票据 → 本地桥 → `CommandExecutor` 原子事务 → Handle 校验 → 事务与回滚结果。

## 唯一来源

- 工具契约：`cadmcp/tool_registry.py`
- 工具执行：`cadmcp/tool_executor.py`
- 专业算法：`cadmcp/domain/architecture/`
- Skill：`copilot_backend/skills/registry.py`
- AutoCAD 路由：`Core/LocalToolBridge.cs`

不在架构内：独立墙/门/窗/房间创编工具、类天正工具栏、三维/BIM 内核、NAS 发布平台。历史实现已移动到上一级备份区。

插件不包含用户登录、积分、套餐、用量或在线更新平台。连接权限由本地桥 token、MCP Host 审批和写操作一次性票据负责；模型密钥由本机插件或 backend 模型配置管理。

详见 [MCP 架构](mcp-architecture.md)、[Planner 设计](planner-design.md) 和 [产品定义](product-prd-v5-semantic-conversion.md)。
