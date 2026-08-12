# ADR-0001：cadmcp 与本地 CAD 事务边界

- 状态：Accepted
- 日期：2026-07-16
- 配置 schema：2
- Bridge protocol：2.0

## 决策

`cadmcp` 是可独立发布的 Python distribution，也是 MCP 工具注册、权限票据、结果协议和建筑领域预览的唯一实现。`copilot_backend` 通过 `cadmcp>=0.2,<0.3` 使用它；backend 下的旧 `architecture.*` 和 `mcp_runtime.*` 入口只承担导入兼容。

Codex、Claude Desktop 或其他 MCP Host 只连接 `cadmcp`。Codex CLI 不作为聊天模型 provider。模型调用由 backend gateway 按显式 `protocol + capabilities` 路由。

所有真实 DWG 写入只能发生在 AutoCAD 进程内的 `LocalToolBridge`：

1. Host 请求 dry-run，cadmcp 生成规范化预览 hash 和一次性 HMAC 票据。
2. 可逆写入需要有效票据；破坏性写入还需要本地用户确认；critical 操作还需 task id。
3. LocalToolBridge 只接收 typed 参数，验证 bridge protocol 2.0 和非空生产 token。
4. C# 在一个 AutoCAD Transaction 内写实体和语义 XRecord，提交后按 Handle 与语义 after-image 复验。
5. 成功结果返回 `wallrb_*` 或 `cadrb_*`；回滚前校验图纸指纹及 after-image/实体签名。

## 结果

- Python 预览不能冒充真实 DWG 成功。
- backend、MCP Host 与 AutoCAD 插件可独立升级，但必须满足 wheel 版本、配置 schema 和 bridge protocol 约束。
- 回滚缓存当前为插件进程内 256 条有界记录；跨插件重启持久化属于后续 ADR。
- AutoCAD 实机流水线必须运行在带交互桌面的自托管 Windows/AutoCAD Runner。

## 被替代入口

`bridge_service/app.py`、`bridge_service/mcp_server.py` 已移除。HTTP 使用 `copilot_backend.http_api.app:app`，MCP 使用安装后的 `cadmcp` 命令。
