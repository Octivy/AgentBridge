from __future__ import annotations

import argparse
import copy
import os
from typing import Any, Dict, Iterable, Optional

from mcp import types
from mcp.server.fastmcp import FastMCP

from cadmcp.tool_executor import CadToolExecutor
from cadmcp.tool_registry import ToolDefinition, get_product_tool, list_product_tools


SERVER_INSTRUCTIONS = (
    "CADMCP connects AI models to the active AutoCAD 2024 document through a local bridge. "
    "Call cad_health_check before a workflow. Read tools are safe. For every "
    "write-capable tool, call it with dry_run=true first, review the preview, "
    "then call again with dry_run=false only after the user approves the change. "
    "Pass the permission_token and preview_hash returned by that exact preview; "
    "tickets expire and can be used only once. Wall, door, and window authoring "
    "tools are maintained outside the default product surface."
)


def _input_schema(tool: ToolDefinition) -> Dict[str, Any]:
    schema = copy.deepcopy(tool.input_schema)
    properties = schema.setdefault("properties", {})
    if tool.dry_run_supported:
        properties.setdefault(
            "dry_run",
            {
                "type": "boolean",
                "default": True,
                "description": "Preview without applying when true. Write tools default to preview mode.",
            },
        )
        properties.setdefault(
            "permission_token",
            {
                "type": "string",
                "description": "One-time capability returned by the approved dry-run preview.",
            },
        )
        properties.setdefault("preview_hash", {"type": "string", "description": "Hash returned by the dry-run preview."})
        properties.setdefault("permission_request_id", {"type": "string"})
        properties.setdefault("confirmed_by_local_user", {"type": "boolean"})
        properties.setdefault("task_id", {"type": "string"})
    properties.setdefault(
        "trace_id",
        {"type": "string", "description": "Optional caller trace identifier."},
    )
    return schema


def _annotations(tool: ToolDefinition) -> types.ToolAnnotations:
    read_only = tool.risk_level == "read_only"
    destructive = tool.risk_level in {"destructive_write", "critical"}
    return types.ToolAnnotations(
        title=tool.display_name,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only,
        openWorldHint=False,
    )


def _mcp_tools(definitions: Iterable[ToolDefinition]) -> list[types.Tool]:
    return [
        types.Tool(
            name=tool.tool_name,
            title=tool.display_name,
            description=tool.description,
            inputSchema=_input_schema(tool),
            annotations=_annotations(tool),
            _meta={
                "cadmcp/category": tool.category,
                "cadmcp/riskLevel": tool.risk_level,
                "cadmcp/dryRunSupported": tool.dry_run_supported,
            },
        )
        for tool in definitions
    ]


def create_mcp_server(
    executor: Optional[CadToolExecutor] = None,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> FastMCP:
    tool_executor = executor or CadToolExecutor()
    server = FastMCP(
        "cadmcp",
        instructions=SERVER_INSTRUCTIONS,
        host=host or os.getenv("CADMCP_HOST", "127.0.0.1"),
        port=port or int(os.getenv("CADMCP_PORT", "8766")),
        stateless_http=True,
        json_response=True,
    )

    @server._mcp_server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return _mcp_tools(list_product_tools())

    @server._mcp_server.call_tool(validate_input=True)
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = get_product_tool(name)
        if definition is None:
            return {
                "ok": False,
                "tool_name": name,
                "summary": f"Unknown CAD tool: {name}",
                "data": None,
                "error_code": "unknown_tool",
                "error_message": f"Unknown CAD tool: {name}",
                "dry_run": None,
                "request_id": None,
                "affected_entities_count": None,
            }

        safe_arguments = dict(arguments or {})
        requested_dry_run = safe_arguments.pop("dry_run", None)
        dry_run = bool(requested_dry_run) if requested_dry_run is not None else bool(definition.dry_run_supported)
        return await tool_executor.execute_tool(
            name,
            safe_arguments,
            caller="cadmcp",
            dry_run=dry_run,
        )

    return server


mcp = create_mcp_server()


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Expose AgentBridge tools through MCP.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("CADMCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("CADMCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CADMCP_PORT", "8766")))
    args = parser.parse_args(argv)

    server = mcp
    if args.host != os.getenv("CADMCP_HOST", "127.0.0.1") or args.port != int(os.getenv("CADMCP_PORT", "8766")):
        server = create_mcp_server(host=args.host, port=args.port)
    server.run(transport=args.transport)


__all__ = ["SERVER_INSTRUCTIONS", "create_mcp_server", "main", "mcp"]
