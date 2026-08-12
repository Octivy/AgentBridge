"""FastMCP server exposing the AgentBridge control plane."""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from control_mcp.service import ControlService, default_control_service


CONTROL_INSTRUCTIONS = (
    "You are the AgentBridge control plane. You manage the bridges between AI agents and local "
    "software (AutoCAD, Blender, SketchUp, Rhino, ...). Inspect configured software with "
    "ab_list_software / ab_software_status, test and start/stop bridges, add/update/remove host "
    "configs, preview and write MCP configs for Codex or Claude, and scaffold a Host Adapter for "
    "software that has no MCP support yet. For write tools always prefer dry-run style workflows "
    "and report the permission/rollback tokens to the user."
)


def create_control_server(service: Optional[ControlService] = None) -> FastMCP:
    control = service or default_control_service
    server = FastMCP(
        "agentbridge",
        instructions=CONTROL_INSTRUCTIONS,
        host=os.getenv("CONTROL_MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTROL_MCP_PORT", "8768")),
        stateless_http=True,
        json_response=True,
    )

    @server._mcp_server.list_tools()
    async def handle_list_tools() -> list:
        return control.list_tools()

    @server._mcp_server.call_tool(validate_input=True)
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await _run_in_thread(control, name, arguments)

    return server


async def _run_in_thread(control: ControlService, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return await control.execute_async(name, arguments)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="AgentBridge control-plane MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("CONTROL_MCP_TRANSPORT", "stdio"),
    )
    args = parser.parse_args(argv)
    create_control_server().run(transport=args.transport)


__all__ = ["CONTROL_INSTRUCTIONS", "create_control_server", "main"]
