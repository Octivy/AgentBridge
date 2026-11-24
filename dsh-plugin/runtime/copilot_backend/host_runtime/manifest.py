"""Manifest validation for the Host Adapter Contract v1."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


MANIFEST_SCHEMA_VERSION = 1

REQUIRED_TOOL_FIELDS = {
    "tool_name",
    "display_name",
    "category",
    "description",
    "input_schema",
    "dry_run_supported",
    "side_effect_level",
    "result_schema",
}


class ManifestValidationError(ValueError):
    pass


def validate_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a host manifest and return the normalized copy.

    Raises ``ManifestValidationError`` when the manifest cannot be used.
    """

    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("manifest must be a JSON object")
    data = dict(manifest)
    if int(data.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError(f"unsupported manifest schema_version: {data.get('schema_version')}")
    for field in ("host_id", "host_kind", "product", "product_version", "protocol_version"):
        if not str(data.get(field) or "").strip():
            raise ManifestValidationError(f"manifest is missing {field}")
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ManifestValidationError("manifest must expose at least one tool")
    normalized_tools = [validate_tool(tool) for tool in tools]
    data["tools"] = normalized_tools
    return data


def validate_tool(tool: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(tool, Mapping):
        raise ManifestValidationError("tool definition must be an object")
    normalized = dict(tool)
    missing = REQUIRED_TOOL_FIELDS - set(normalized)
    if missing:
        raise ManifestValidationError(f"tool is missing fields: {sorted(missing)}")
    tool_name = str(normalized.get("tool_name") or "").strip()
    if not tool_name:
        raise ManifestValidationError("tool_name must not be empty")
    input_schema = normalized.get("input_schema")
    if not isinstance(input_schema, Mapping) or input_schema.get("type") != "object":
        raise ManifestValidationError(f"tool {tool_name} input_schema must be a JSON Schema object")
    normalized["tool_name"] = tool_name
    return normalized


def merge_tool_namespaces(manifests: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Namespace host tools as ``<host_kind>_<tool_name>`` for the MCP surface."""

    merged: List[Dict[str, Any]] = []
    for manifest in manifests:
        host_kind = str(manifest.get("host_kind") or "host").strip()
        for tool in manifest.get("tools") or []:
            prefixed = dict(tool)
            tool_name = str(tool["tool_name"])
            prefix = f"{host_kind}_"
            prefixed["tool_name"] = tool_name if tool_name.startswith(prefix) else f"{prefix}{tool_name}"
            merged.append(prefixed)
    return merged


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "ManifestValidationError",
    "merge_tool_namespaces",
    "validate_manifest",
    "validate_tool",
]
