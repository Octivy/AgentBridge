"""Rhino ``rhinoscriptsyntax`` backend shared by the host adapter.

``rhinoscriptsyntax`` is imported lazily so this module can be imported outside
Rhino (unit tests). All functions assume they run inside Rhino's Python.
"""

# -*- coding: utf-8 -*-

from typing import Any, Dict

try:
    import rhinoscriptsyntax as rs  # type: ignore
except ImportError:  # allow import outside Rhino
    rs = None


TOOLS = [
    {
        "tool_name": "rhino_scene_summary",
        "display_name": "场景摘要",
        "category": "analysis",
        "description": "汇总当前 Rhino 文档的对象数量、图层与文件名。",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "dry_run_supported": False,
        "side_effect_level": "none",
        "result_schema": {"type": "object"},
    },
    {
        "tool_name": "rhino_create_box",
        "display_name": "创建长方体",
        "category": "modeling",
        "description": "预览并创建一个长方体对象，可回滚删除。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "size": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
]


def require_rs() -> None:
    if rs is None:
        raise RuntimeError("rhinoscriptsyntax is required; run inside Rhino")


def scene_summary() -> Dict[str, Any]:
    require_rs()
    object_ids = rs.Objects() or []
    layers = []
    try:
        layers = rs.LayerNames() or []
    except Exception:  # noqa: BLE001
        pass
    return {
        "schema_version": 1,
        "source": "rhino",
        "document": rs.DocumentName() or "",
        "object_count": len(object_ids),
        "layers": layers,
    }


def snapshot(scope: Dict[str, Any]) -> Dict[str, Any]:
    del scope
    return {"ok": True, "snapshot": scene_summary()}


_ROLLBACK_LEDGER: Dict[str, tuple] = {}


def create_box(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    require_rs()
    size = [float(value) for value in (arguments.get("size") or [2.0, 2.0, 2.0])]
    location = [float(value) for value in (arguments.get("location") or [0.0, 0.0, 0.0])]
    if len(size) != 3 or len(location) != 3:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "size and location must contain 3 numbers"}
    name = str(arguments.get("name") or "AgentBridgeBox").strip()
    half = [value / 2.0 for value in size]
    corners = [
        (
            location[0] + dx * half[0],
            location[1] + dy * half[1],
            location[2] + dz * half[2],
        )
        for dx in (-1, 1)
        for dy in (-1, 1)
        for dz in (-1, 1)
    ]
    preview = {"object_name": name, "size": size, "location": location, "corner_count": len(corners)}
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}

    guid = rs.AddBox(corners)
    if not guid:
        return {"ok": False, "error_code": "execution_error", "error_message": "Rhino failed to create the box"}
    try:
        rs.ObjectName(guid, name)
    except Exception:  # noqa: BLE001
        pass
    token = f"rhino-box-{name}"
    _ROLLBACK_LEDGER[token] = ("box", {"name": name, "guid": str(guid)})
    return {
        "ok": True,
        "result": {"object_name": name, "object_id": str(guid), "size": size, "location": location},
        "dry_run": False,
        "rollback_token": token,
    }


def runner(tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if tool_name == "rhino_scene_summary":
        return {"ok": True, "result": scene_summary(), "dry_run": False}
    if tool_name == "rhino_create_box":
        return create_box(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}


def rollback(rollback_token: str) -> Dict[str, Any]:
    require_rs()
    entry = _ROLLBACK_LEDGER.pop(rollback_token, None)
    if entry is None:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback token"}
    kind, payload = entry
    if kind == "box":
        deleted = rs.DeleteObject(payload["guid"])
        return {
            "ok": True,
            "result": {"rolled_back": True, "object_name": payload["name"], "deleted": bool(deleted)},
        }
    return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback kind"}


__all__ = ["TOOLS", "create_box", "require_rs", "rollback", "runner", "scene_summary", "snapshot"]
