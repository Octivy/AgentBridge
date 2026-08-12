"""FastMCP server exposing tools from all discovered host adapters."""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from host_mcp.runtime import HostMcpExecutor


SERVER_INSTRUCTIONS = (
    "HOSTMCP exposes tools from external software hosts (Blender, SketchUp, "
    "Rhino, AutoCAD...) that registered with the AgentBridge client. Tool names "
    "are namespaced as <host>_<tool>. Read tools are safe. For every write-capable "
    "tool, call it with dry_run=true first, review the preview, then call again "
    "with dry_run=false only after the user approves the change. Pass the "
    "permission_token and preview_hash returned by that exact preview; tickets "
    "expire and can be used only once."
)


def create_mcp_server(
    executor: Optional[HostMcpExecutor] = None,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> FastMCP:
    host_executor = executor or HostMcpExecutor()
    server = FastMCP(
        "hostmcp",
        instructions=SERVER_INSTRUCTIONS,
        host=host or os.getenv("HOSTMCP_HOST", "127.0.0.1"),
        port=port or int(os.getenv("HOSTMCP_PORT", "8767")),
        stateless_http=True,
        json_response=True,
    )

    @server._mcp_server.list_tools()
    async def handle_list_tools() -> list:
        return host_executor.list_tools()

    @server._mcp_server.call_tool(validate_input=True)
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await host_executor.execute_tool(name, arguments)

    return server


mcp = create_mcp_server()


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Expose external host tools through MCP.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("HOSTMCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("HOSTMCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HOSTMCP_PORT", "8767")))
    parser.add_argument("--registry-dir", default=os.getenv("HOSTMCP_REGISTRY_DIR", ""))
    args = parser.parse_args(argv)

    executor = HostMcpExecutor(registry_dir=args.registry_dir) if args.registry_dir else None
    server = create_mcp_server(executor, host=args.host, port=args.port)
    server.run(transport=args.transport)


__all__ = ["SERVER_INSTRUCTIONS", "create_mcp_server", "main", "mcp"]
