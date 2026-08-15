"""Validate the three MCP servers exactly as an MCP client (DSH) would spawn them.

For each server: launch via stdio, initialize, list tools, print the names.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
ROOT = r"H:\codex\AgentBridge"

SERVERS = {
    "hostmcp": {
        "command": POWERSHELL,
        "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ROOT + r"\scripts\start-hostmcp.ps1"],
    },
    "cadmcp": {
        "command": POWERSHELL,
        "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ROOT + r"\scripts\start-cadmcp.ps1"],
    },
    "agentbridge": {
        "command": r"C:\Users\chang_k\AppData\Local\Programs\Python\Python311\python.exe",
        "args": ["-m", "control_mcp"],
        "cwd": ROOT + r"\copilot_backend",
    },
}


async def probe(name: str, spec: dict) -> None:
    params = StdioServerParameters(
        command=spec["command"],
        args=spec.get("args", []),
        cwd=spec.get("cwd"),
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                tools = await asyncio.wait_for(session.list_tools(), timeout=30)
                names = sorted(tool.name for tool in tools.tools)
                print(f"[{name}] OK  tools={len(names)}")
                for tool_name in names:
                    print(f"    - {tool_name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] FAILED: {type(exc).__name__}: {exc}")


async def main() -> None:
    for name, spec in SERVERS.items():
        await probe(name, spec)


if __name__ == "__main__":
    asyncio.run(main())
