"""Generate and persist MCP server configs for external agents (Codex, Claude)."""

from __future__ import annotations

import json
import os
import sys
import tomllib
import tomli_w
from pathlib import Path
from typing import Dict, List, Optional

from host_config.models import HostAdapterConfig
from host_config.store import HostConfigStore, default_config_path
from mcp_registry.models import McpServerEntry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def codex_config_path() -> Path:
    base = os.getenv("USERPROFILE") or os.getenv("HOME") or str(Path.home())
    return Path(base) / ".codex" / "config.toml"


def _entry_from_config(config: HostAdapterConfig, name: str) -> McpServerEntry:
    return McpServerEntry(
        name=name,
        command=config.launch.command,
        args=list(config.launch.args),
        cwd=config.launch.cwd,
        env_vars=list(config.launch.env_vars),
        approval_mode="approve",
        enabled=config.enabled,
        required=False,
        startup_timeout_sec=20,
        tool_timeout_sec=60,
    )


def build_mcp_servers(store: Optional[HostConfigStore] = None) -> List[McpServerEntry]:
    """Derive the MCP server set from enabled host configurations.

    cadmcp covers AutoCAD; hostmcp aggregates every other registered host
    (Blender, SketchUp, Rhino, ...). Only hosts with a launch command produce
    a server entry.
    """

    store = store or HostConfigStore(path=default_config_path())
    candidates = [config for config in store.list() if config.enabled and config.launch.command.strip()]

    cadmcp = next((c for c in candidates if c.host_kind == "autocad" or c.host_id == "autocad"), None)
    hostmcp = next(
        (
            c
            for c in candidates
            if c.host_kind != "autocad" and c.host_id != "autocad" and "hostmcp" in c.launch.command.lower()
        ),
        next((c for c in candidates if c.host_kind != "autocad" and c.host_id != "autocad"), None),
    )

    entries: List[McpServerEntry] = []
    if cadmcp is not None:
        entries.append(_entry_from_config(cadmcp, "cadmcp"))
    if hostmcp is not None:
        entries.append(_entry_from_config(hostmcp, "hostmcp"))
    entries.append(
        McpServerEntry(
            name="agentbridge",
            command=sys.executable,
            args=["-m", "control_mcp"],
            cwd=str(Path(__file__).resolve().parents[1]),
            approval_mode="approve",
            enabled=True,
        )
    )
    return entries


def _server_toml_table(entry: McpServerEntry) -> Dict[str, object]:
    table: Dict[str, object] = {
        "command": entry.command,
        "args": list(entry.args),
        "enabled": entry.enabled,
        "required": entry.required,
        "startup_timeout_sec": entry.startup_timeout_sec,
        "tool_timeout_sec": entry.tool_timeout_sec,
        "default_tools_approval_mode": entry.approval_mode,
    }
    if entry.cwd:
        table["cwd"] = entry.cwd
    if entry.env_vars:
        table["env_vars"] = list(entry.env_vars)
    return table


def render_codex_toml(entries: List[McpServerEntry]) -> str:
    """Render the `[mcp_servers.X]` blocks for preview."""

    payload: Dict[str, object] = {"mcp_servers": {entry.name: _server_toml_table(entry) for entry in entries}}
    return tomli_w.dumps(payload).rstrip() + "\n"


def write_codex_config(
    entries: List[McpServerEntry],
    target: Optional[Path] = None,
) -> Dict[str, object]:
    """Merge MCP servers into the user-level Codex config, preserving everything else."""

    target = Path(target or codex_config_path())
    data: Dict[str, object] = {}
    if target.exists():
        try:
            data = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            backup = target.with_suffix(".toml.bak")
            try:
                target.replace(backup)
            except OSError:
                pass
            data = {}

    servers = data.setdefault("mcp_servers", {})
    assert isinstance(servers, dict)
    for entry in entries:
        servers[entry.name] = _server_toml_table(entry)

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".toml.tmp")
    temp.write_text(tomli_w.dumps(data), encoding="utf-8")
    os.replace(temp, target)
    return {"path": str(target), "servers": [entry.name for entry in entries]}


def build_claude_json(entries: List[McpServerEntry]) -> Dict[str, object]:
    """Build the Claude Code `.mcp.json` payload (absolute stdio commands)."""

    servers: Dict[str, object] = {}
    for entry in entries:
        servers[entry.name] = {
            "type": "stdio",
            "command": entry.command,
            "args": list(entry.args),
            "env": {},
        }
    return {"mcpServers": servers}


def write_claude_config(
    entries: List[McpServerEntry],
    target: Optional[Path] = None,
) -> Dict[str, object]:
    """Write the Claude Code project `.mcp.json` (existing file is backed up)."""

    target = Path(target or _repo_root() / ".mcp.json")
    if target.exists():
        backup = target.with_suffix(".json.bak")
        try:
            target.replace(backup)
        except OSError:
            pass
    payload = build_claude_json(entries)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, target)
    return {"path": str(target), "servers": [entry.name for entry in entries]}


__all__ = [
    "build_claude_json",
    "build_mcp_servers",
    "codex_config_path",
    "render_codex_toml",
    "write_claude_config",
    "write_codex_config",
]
