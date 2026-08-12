from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "cadmcp"])
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {
                "cad_health_check",
                "get_drawing_snapshot",
                "arch_extract_outer_outline",
                "arch_draw_outer_outline",
                "arch_suggest_layer_mapping",
                "arch_apply_layer_mapping",
                "cad_rollback_transaction",
            }
            missing = required - names
            if missing:
                raise RuntimeError(f"MCP handshake succeeded but required tools are missing: {sorted(missing)}")
            forbidden = {
                "arch_create_wall",
                "arch_place_opening",
                "arch_create_room",
                "arch_extract_enclosed_spaces",
                "arch_draw_enclosed_spaces",
                "arch_apply_layer_standard",
            } & names
            if forbidden:
                raise RuntimeError(f"Independent authoring tools leaked into product MCP: {sorted(forbidden)}")
            print(f"server={result.serverInfo.name} tools={len(names)}")


if __name__ == "__main__":
    asyncio.run(main())
