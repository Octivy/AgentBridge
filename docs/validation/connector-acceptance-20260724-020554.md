# AgentBridge 连接器验收报告

- 生成时间：2026-07-23T18:05:54.504671+00:00
- 总状态：`failed`
- 敏感信息已脱敏：`true`

## 检查结果

| 检查 | 状态 | 结论 |
| --- | --- | --- |
| Codex / MCP Host contract | `passed` | Project-scoped Codex configuration and write approval policy are present. |
| Second MCP Host | `blocked` | Claude Code is installed and project configuration exists, but its project MCP approval/connection is not complete. |
| Backend five-layer diagnostics | `passed` | Backend returned 5 diagnostic components with overall status ok. |
| CADMCP repeated initialization and discovery | `passed` | 20/20 MCP sessions initialized with the exact 13-tool contract. |
| Online model provider | `failed` | 0/10 planned minimax requests succeeded. Remaining calls were skipped after a non-transient credential/configuration error. |
| AutoCAD local bridge | `passed` | 20/20 bridge health and drawing snapshot reads succeeded. |

## 恢复动作

- **Second MCP Host**：Open Claude Code in this project, approve the project cadmcp server, verify it is connected, then rerun acceptance.
- **Online model provider**：Replace or authorize the configured provider credential, then rerun the 10-call gate.

## 环境摘要

```json
{
  "platform": "win32",
  "python": "3.13.7",
  "autocad_running": true,
  "backend_port_open": true,
  "bridge_port_open": true,
  "ollama_port_open": false,
  "codex_available": true,
  "claude_host_available": true,
  "claude_mcp_configured": true,
  "claude_mcp_status": "pending_approval",
  "provider_configuration": {
    "minimax": true,
    "openai": false,
    "anthropic": false,
    "deepseek": false,
    "ollama": false
  }
}
```
