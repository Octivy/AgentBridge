"""Rhino backend shared by the host adapter.

All document access goes through ``_active_doc()`` so it always targets the
document the user currently sees.  The host adapter executes every tool on
Rhino's main thread (see ``background_host.py`` / ``host.RhinoExecutor``),
because Rhino documents are not thread-safe and ``RhinoDoc.ActiveDoc`` is not
reliable from background threads.
"""

from __future__ import annotations

import os
from typing import Any, Dict

try:
    import Rhino  # type: ignore  # noqa: F401
except ImportError:  # allow import outside Rhino
    Rhino = None

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


def _active_doc():
    if Rhino is None:
        raise RuntimeError("Rhino is required; run inside Rhino")
    return Rhino.RhinoDoc.ActiveDoc


def _object_count(doc) -> int:
    """Count live objects by iterating the object table.

    ``ObjectTable.Count`` has known staleness quirks in Rhino 8, so iterate the
    table instead; the enumerator only yields non-deleted objects.
    """
    try:
        count = 0
        for _ in doc.Objects:
            count += 1
        return count
    except Exception:  # noqa: BLE001
        try:
            return doc.Objects.Count
        except Exception:  # noqa: BLE001
            return 0


def _find_object(doc, guid_str: str):
    for obj in doc.Objects:
        try:
            if str(obj.Id) == guid_str:
                return obj
        except Exception:  # noqa: BLE001
            continue
    return None


def scene_summary() -> Dict[str, Any]:
    doc = _active_doc()
    object_count = _object_count(doc)
    layer_names = [layer.FullPath for layer in doc.Layers]
    document_name = doc.Name or ""
    if not document_name and rs is not None:
        try:
            document_name = rs.DocumentName() or ""
        except Exception:  # noqa: BLE001
            pass
    return {
        "schema_version": 1,
        "source": "rhino",
        "document": document_name,
        "object_count": object_count,
        "layers": layer_names,
    }


def snapshot(scope: Dict[str, Any]) -> Dict[str, Any]:
    del scope
    return {"ok": True, "snapshot": scene_summary()}


_ROLLBACK_LEDGER: Dict[str, tuple] = {}


def create_box(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    size = [float(value) for value in (arguments.get("size") or [2.0, 2.0, 2.0])]
    location = [float(value) for value in (arguments.get("location") or [0.0, 0.0, 0.0])]
    if len(size) != 3 or len(location) != 3:
        return {
            "ok": False,
            "error_code": "invalid_arguments",
            "error_message": "size and location must contain 3 numbers",
        }
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

    doc = _active_doc()
    xs = [corner[0] for corner in corners]
    ys = [corner[1] for corner in corners]
    zs = [corner[2] for corner in corners]
    geometry = Rhino.Geometry
    bbox = geometry.BoundingBox(
        geometry.Point3d(min(xs), min(ys), min(zs)),
        geometry.Point3d(max(xs), max(ys), max(zs)),
    )
    box = geometry.Box(bbox)
    brep = box.ToBrep()
    oid = doc.Objects.AddBrep(brep, None)
    guid = str(oid)
    if not guid or guid == "00000000-0000-0000-0000-000000000000":
        return {"ok": False, "error_code": "execution_error", "error_message": "Rhino failed to create the box"}
    try:
        rhino_object = doc.Objects[oid]
        rhino_object.Attributes.Name = name
        rhino_object.CommitChanges()
    except Exception:  # noqa: BLE001
        pass
    token = f"rhino-box-{name}"
    _ROLLBACK_LEDGER[token] = ("box", {"name": name, "guid": guid})
    return {
        "ok": True,
        "result": {"object_name": name, "object_id": guid, "size": size, "location": location},
        "dry_run": False,
        "rollback_token": token,
    }


def runner(tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if tool_name == "rhino_scene_summary":
        return {"ok": True, "result": scene_summary(), "dry_run": False}
    if tool_name == "rhino_create_box":
        return create_box(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}


def _rollback_log(message: str) -> None:
    try:
        log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-rollback.log")
        try:
            import io

            with io.open(log_path, "a", encoding="utf-8") as handle:
                handle.write(str(message) + "\n")
        except Exception:  # noqa: BLE001
            with open(log_path, "a") as handle:
                handle.write(str(message) + "\n")
    except Exception:  # noqa: BLE001
        pass


def rollback(rollback_token: str) -> Dict[str, Any]:
    doc = _active_doc()
    entry = _ROLLBACK_LEDGER.pop(rollback_token, None)
    if entry is None:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback token"}
    kind, payload = entry
    if kind != "box":
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback kind"}
    guid_str = payload["guid"]
    _rollback_log("begin rollback=%s guid=%s count=%s" % (rollback_token, guid_str, _object_count(doc)))
    existed = _find_object(doc, guid_str) is not None
    _rollback_log("exists before: %s" % existed)
    if existed:
        # Strategy 1: RhinoCommon Delete with a System.Guid.
        try:
            import System  # noqa: F401

            result = doc.Objects.Delete(System.Guid(guid_str), True)
            _rollback_log("Objects.Delete(Guid,True) -> %r exists=%s" % (result, _find_object(doc, guid_str) is not None))
        except Exception as exc:  # noqa: BLE001
            _rollback_log("Objects.Delete(Guid,True) EXC: %s" % exc)
        # Strategy 2: RhinoCommon Delete with the live ObjectId.
        live = _find_object(doc, guid_str)
        if live is not None:
            try:
                result = doc.Objects.Delete(live.Id, True)
                _rollback_log("Objects.Delete(ObjectId,True) -> %r exists=%s" % (result, _find_object(doc, guid_str) is not None))
            except Exception as exc:  # noqa: BLE001
                _rollback_log("Objects.Delete(ObjectId,True) EXC: %s" % exc)
        # Strategy 3: rhinoscriptsyntax.
        if _find_object(doc, guid_str) is not None:
            try:
                require_rs()
                result = rs.DeleteObject(guid_str)
                _rollback_log("rs.DeleteObject -> %r exists=%s" % (result, _find_object(doc, guid_str) is not None))
            except Exception as exc:  # noqa: BLE001
                _rollback_log("rs.DeleteObject EXC: %s" % exc)
    deleted = _find_object(doc, guid_str) is None
    _rollback_log("final deleted=%s count=%s" % (deleted, _object_count(doc)))
    return {
        "ok": True,
        "result": {"rolled_back": True, "object_name": payload["name"], "deleted": deleted},
    }


__all__ = ["TOOLS", "create_box", "require_rs", "rollback", "runner", "scene_summary", "snapshot"]
