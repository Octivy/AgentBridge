"""Multi-host MCP tool surface for the Host Adapter Contract v1."""

from host_mcp.runtime import HostMcpExecutor
from host_mcp.server import create_mcp_server

__all__ = ["HostMcpExecutor", "create_mcp_server"]
