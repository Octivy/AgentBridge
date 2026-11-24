"""Collect host tools and convert them to MCP tool definitions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from mcp import types

from host_runtime.client import HostClient, HostError
from host_runtime.manifest import ManifestValidationError, validate_manifest
from host_runtime.registry import discover_hosts


@dataclass(frozen=True)
class HostTool:
    host_id: str
    host_kind: str
    endpoint: str
    token: str
    tool_name: str
    definition: Dict[str, Any]


def namespaced_tool_name(host_kind: str, tool_name: str) -> str:
    kind = str(host_kind or "host").strip()
    name = str(tool_name or "").strip()
    prefix = f"{kind}_"
    return name if name.startswith(prefix) else f"{prefix}{name}"


def tool_risk_level(tool: Mapping[str, Any]) -> str:
    risk = str(tool.get("risk_level") or "").strip().lower()
    if risk:
        return risk
    side_effect = str(tool.get("side_effect_level") or "none").strip().lower()
    return "read_only" if side_effect == "none" else "reversible_write"


def collect_host_tools(registry_dir) -> Tuple[List[HostTool], List[Dict[str, Any]]]:
    """Fetch and validate manifests from all discovered hosts."""

    tools: List[HostTool] = []
    errors: List[Dict[str, Any]] = []
    for registration in discover_hosts(registry_dir):
        try:
            client = HostClient(registration.endpoint, registration.token)
            manifest = validate_manifest(client.manifest())
        except (HostError, ManifestValidationError) as exc:
            errors.append(
                {
                    "host_id": registration.host_id,
                    "error_code": getattr(exc, "error_code", "manifest_error"),
                    "message": str(exc),
                }
            )
            continue
        for tool in manifest.get("tools") or []:
            tools.append(
                HostTool(
                    host_id=registration.host_id,
                    host_kind=registration.host_kind,
                    endpoint=registration.endpoint,
                    token=registration.token,
                    tool_name=namespaced_tool_name(registration.host_kind, tool["tool_name"]),
                    definition=dict(tool),
                )
            )
    return tools, errors


def augment_input_schema(tool: Mapping[str, Any]) -> Dict[str, Any]:
    schema = copy.deepcopy(tool.get("input_schema") or {"type": "object", "properties": {}})
    properties = schema.setdefault("properties", {})
    if bool(tool.get("dry_run_supported")):
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
            {"type": "string", "description": "One-time capability returned by the approved dry-run preview."},
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


def to_mcp_tool(host_tool: HostTool) -> types.Tool:
    definition = host_tool.definition
    risk = tool_risk_level(definition)
    return types.Tool(
        name=host_tool.tool_name,
        title=definition.get("display_name") or host_tool.tool_name,
        description=definition.get("description") or "",
        inputSchema=augment_input_schema(definition),
        annotations=types.ToolAnnotations(
            title=definition.get("display_name") or host_tool.tool_name,
            readOnlyHint=risk == "read_only",
            destructiveHint=risk in {"destructive_write", "critical"},
            idempotentHint=risk == "read_only",
            openWorldHint=False,
        ),
        _meta={
            "hostmcp/hostId": host_tool.host_id,
            "hostmcp/hostKind": host_tool.host_kind,
            "hostmcp/category": definition.get("category") or "general",
            "hostmcp/riskLevel": risk,
            "hostmcp/dryRunSupported": bool(definition.get("dry_run_supported")),
        },
    )


__all__ = [
    "HostTool",
    "augment_input_schema",
    "collect_host_tools",
    "namespaced_tool_name",
    "to_mcp_tool",
    "tool_risk_level",
]
