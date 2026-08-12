"""MCP 接入管理：为 Codex / Claude 等 Agent 生成并写入桥接配置。"""

from mcp_registry.service import (
    build_claude_json,
    build_mcp_servers,
    render_codex_toml,
    write_claude_config,
    write_codex_config,
)

__all__ = [
    "build_claude_json",
    "build_mcp_servers",
    "render_codex_toml",
    "write_claude_config",
    "write_codex_config",
]
