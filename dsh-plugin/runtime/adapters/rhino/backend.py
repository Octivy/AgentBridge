# -*- coding: utf-8 -*-
"""Rhino backend shared by the host adapter.

All document access goes through ``_active_doc()`` so it always targets the
document the user currently sees.  The host adapter executes every tool on
Rhino's main thread (see ``background_host.py`` / ``host.RhinoExecutor``),
because Rhino documents are not thread-safe and ``RhinoDoc.ActiveDoc`` is not
reliable from background threads.
"""

from __future__ import absolute_import, division, print_function

import os

try:
    import Rhino  # type: ignore  # noqa: F401
except ImportError:  # allow import outside Rhino
    Rhino = None

try:
    import rhinoscriptsyntax as rs  # type: ignore
except ImportError:  # allow import outside Rhino
    rs = None


def _debug_log(message):
    try:
        import io
        import os

        log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-layer-debug.log")
        with io.open(log_path, "a", encoding="utf-8") as handle:
            handle.write(str(message) + "\n")
    except Exception:  # noqa: BLE001
        pass


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
        "tool_name": "rhino_get_objects",
        "display_name": "查询场景对象",
        "category": "analysis",
        "description": "列出当前场景对象（ID、图层、名称、类型、包围盒），可按图层过滤，供 Agent 观察模型后再决策。",
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {"type": "string", "description": "只返回该图层的对象；省略则返回全部图层"},
                "limit": {"type": "integer", "description": "最多返回多少对象，默认 500"},
            },
            "additionalProperties": False,
        },
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
                "layer": {"type": "string"},
                "layer_color": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
    {
        "tool_name": "rhino_delete_object",
        "display_name": "删除对象",
        "category": "modeling",
        "description": "按对象 ID 删除场景中的对象（Agent 循环的修改步骤）。",
        "input_schema": {
            "type": "object",
            "properties": {"object_id": {"type": "string"}},
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
    },
    {
        "tool_name": "rhino_union_layer",
        "display_name": "合并图层实体",
        "category": "modeling",
        "description": "把指定图层上的所有长方体/曲面做布尔并集，合并为一个整体（消除交接处的内部边线）。",
        "input_schema": {
            "type": "object",
            "properties": {"layer": {"type": "string"}},
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
    },
]


def require_rs():
    if rs is None:
        raise RuntimeError("rhinoscriptsyntax is required; run inside Rhino")


def _active_doc():
    if Rhino is None:
        raise RuntimeError("Rhino is required; run inside Rhino")
    return Rhino.RhinoDoc.ActiveDoc


def _object_count(doc):
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


def _find_object(doc, guid_str):
    for obj in doc.Objects:
        try:
            if str(obj.Id) == guid_str:
                return obj
        except Exception:  # noqa: BLE001
            continue
    return None


def _ensure_layer(doc, name, color_hex=""):
    """Find or create a layer; returns its index.  Falls back to 0 on error."""
    try:
        index = -1
        for layer in doc.Layers:
            try:
                if layer.Name == name:
                    index = layer.LayerIndex
                    break
            except Exception:  # noqa: BLE001
                continue
        if index < 0:
            try:
                index = doc.Layers.Add(name)
            except Exception:  # noqa: BLE001
                # Rhino 8 的 LayerTable.Add(str) 不可用，用 rhinoscriptsyntax。
                _debug_log("ensure_layer Add(str) failed, using rs.AddLayer")
                require_rs()
                if color_hex:
                    try:
                        import System.Drawing

                        value = int(str(color_hex).strip().lstrip("#"), 16)
                        rs.AddLayer(name, System.Drawing.Color.FromArgb(255, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF))
                    except Exception:  # noqa: BLE001
                        rs.AddLayer(name)
                else:
                    rs.AddLayer(name)
                for layer in doc.Layers:
                    try:
                        if layer.Name == name:
                            index = layer.LayerIndex
                            break
                    except Exception:  # noqa: BLE001
                        continue
        if color_hex and index >= 0:
            try:
                import System.Drawing

                value = int(str(color_hex).strip().lstrip("#"), 16)
                layer = doc.Layers[index]
                layer.Color = System.Drawing.Color.FromArgb(
                    255,
                    (value >> 16) & 0xFF,
                    (value >> 8) & 0xFF,
                    value & 0xFF,
                )
            except Exception:  # noqa: BLE001
                pass
        _debug_log("ensure_layer ok name=%s index=%s" % (name, index))
        return index
    except Exception as exc:  # noqa: BLE001
        _debug_log("ensure_layer EXC name=%s: %r" % (name, exc))
        return 0


def scene_summary():
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


def get_objects(arguments, dry_run):
    """List objects with id/layer/name/type/bbox so the Agent can observe the scene."""
    del dry_run
    layer = str(arguments.get("layer") or "").strip()
    try:
        limit = max(1, min(int(arguments.get("limit") or 500), 5000))
    except Exception:  # noqa: BLE001
        limit = 500
    doc = _active_doc()

    layer_index = -1
    if layer:
        for existing in doc.Layers:
            try:
                if existing.Name == layer:
                    layer_index = existing.LayerIndex
                    break
            except Exception:  # noqa: BLE001
                continue
        if layer_index < 0:
            return {"ok": False, "error_code": "execution_error", "error_message": "layer not found: %s" % layer}

    layer_names = {}
    for existing in doc.Layers:
        try:
            layer_names[existing.LayerIndex] = existing.Name
        except Exception:  # noqa: BLE001
            continue

    objects = []
    total = 0
    for obj in doc.Objects:
        try:
            if layer_index >= 0 and obj.Attributes.LayerIndex != layer_index:
                continue
        except Exception:  # noqa: BLE001
            continue
        total += 1
        if len(objects) >= limit:
            continue
        entry = {"id": str(obj.Id)}
        try:
            entry["layer"] = layer_names.get(obj.Attributes.LayerIndex, str(obj.Attributes.LayerIndex))
        except Exception:  # noqa: BLE001
            pass
        try:
            if obj.Attributes.Name:
                entry["name"] = obj.Attributes.Name
        except Exception:  # noqa: BLE001
            pass
        try:
            geometry = obj.Geometry
            entry["type"] = type(geometry).__name__
            if hasattr(geometry, "Faces"):
                try:
                    entry["faces"] = geometry.Faces.Count
                except Exception:  # noqa: BLE001
                    pass
            try:
                if geometry.IsSolid:
                    entry["solid"] = True
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        try:
            bbox = obj.Geometry.GetBoundingBox(True)
            entry["bbox"] = [
                bbox.Min.X, bbox.Min.Y, bbox.Min.Z,
                bbox.Max.X, bbox.Max.Y, bbox.Max.Z,
            ]
        except Exception:  # noqa: BLE001
            pass
        objects.append(entry)

    return {
        "ok": True,
        "result": {
            "layer": layer or None,
            "count": len(objects),
            "total_matching": total,
            "truncated": total > len(objects),
            "objects": objects,
        },
    }


def snapshot(scope):
    del scope
    return {"ok": True, "snapshot": scene_summary()}


_ROLLBACK_LEDGER = {}


def create_box(arguments, dry_run):
    size = [float(value) for value in (arguments.get("size") or [2.0, 2.0, 2.0])]
    location = [float(value) for value in (arguments.get("location") or [0.0, 0.0, 0.0])]
    if len(size) != 3 or len(location) != 3:
        return {
            "ok": False,
            "error_code": "invalid_arguments",
            "error_message": "size and location must contain 3 numbers",
        }
    name = str(arguments.get("name") or "AgentBridgeBox").strip()
    layer = str(arguments.get("layer") or "").strip()
    layer_color = str(arguments.get("layer_color") or "").strip()
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
    attributes = None
    if layer or layer_color:
        try:
            attributes = Rhino.DocObjects.ObjectAttributes()
            attributes.LayerIndex = _ensure_layer(doc, layer or "Default", layer_color)
        except Exception as exc:  # noqa: BLE001
            _debug_log("create_box attrs EXC: %r" % (exc,))
            attributes = None
    oid = doc.Objects.AddBrep(brep, attributes)
    guid = str(oid)
    if not guid or guid == "00000000-0000-0000-0000-000000000000":
        return {"ok": False, "error_code": "execution_error", "error_message": "Rhino failed to create the box"}
    try:
        rhino_object = doc.Objects.FindId(oid)
        if rhino_object is not None:
            attrs = rhino_object.Attributes
            attrs.Name = name
            rhino_object.CommitChanges()
    except Exception as exc:  # noqa: BLE001
        _debug_log("create_box name (RhinoCommon) EXC: %r" % (exc,))
        try:
            require_rs()
            rs.ObjectName(oid, name)
        except Exception as exc2:  # noqa: BLE001
            _debug_log("create_box name (rs) EXC: %r" % (exc2,))
    # Unique rollback token per object so same-named boxes never collide.
    token = "rhino-box-%s-%s" % (name, guid[:8])
    _ROLLBACK_LEDGER[token] = ("box", {"name": name, "guid": guid})
    return {
        "ok": True,
        "result": {
            "object_name": name,
            "object_id": guid,
            "size": size,
            "location": location,
            "layer": layer,
        },
        "dry_run": False,
        "rollback_token": token,
    }


def delete_object(arguments, dry_run):
    """Delete one object by id (the modify step of the agent loop)."""
    object_id = str(arguments.get("object_id") or "").strip()
    if not object_id:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "object_id is required"}
    doc = _active_doc()
    obj = _find_object(doc, object_id)
    if obj is None:
        return {"ok": False, "error_code": "not_found", "error_message": "object not found: %s" % object_id}
    if dry_run:
        return {"ok": True, "result": {"object_id": object_id, "would_delete": True}, "dry_run": True}
    try:
        doc.Objects.Delete(obj.Id, True)
    except Exception as exc:  # noqa: BLE001
        _debug_log("delete_object RhinoCommon EXC: %r" % (exc,))
    if _find_object(doc, object_id) is not None:
        try:
            require_rs()
            rs.DeleteObject(object_id)
        except Exception as exc:  # noqa: BLE001
            _debug_log("delete_object rs EXC: %r" % (exc,))
    deleted = _find_object(doc, object_id) is None
    return {
        "ok": deleted,
        "result": {"object_id": object_id, "deleted": deleted},
        "error_message": None if deleted else "delete failed",
    }


def union_layer(arguments, dry_run):
    """Boolean-union all Breps on a layer into a single solid."""
    layer = str(arguments.get("layer") or "").strip()
    if not layer:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "layer is required"}
    doc = _active_doc()
    layer_index = -1
    for existing in doc.Layers:
        try:
            if existing.Name == layer:
                layer_index = existing.LayerIndex
                break
        except Exception:  # noqa: BLE001
            continue
    if layer_index < 0:
        return {"ok": False, "error_code": "execution_error", "error_message": "layer not found: %s" % layer}

    breps = []
    object_ids = []
    for obj in doc.Objects:
        try:
            if obj.Attributes.LayerIndex != layer_index:
                continue
        except Exception:  # noqa: BLE001
            continue
        try:
            geometry = obj.Geometry
        except Exception:  # noqa: BLE001
            geometry = None
        if geometry is None or not isinstance(geometry, Rhino.Geometry.Brep):
            continue
        breps.append(geometry)
        object_ids.append(obj.Id)

    if not breps:
        return {"ok": True, "result": {"layer": layer, "before": 0, "after": 0, "unioned": False}}
    if dry_run:
        return {"ok": True, "result": {"layer": layer, "before": len(breps), "dry_run": True}}

    _debug_log("union_layer start layer=%s breps=%d" % (layer, len(breps)))

    def add_results(result_breps):
        attributes = Rhino.DocObjects.ObjectAttributes()
        attributes.LayerIndex = layer_index
        new_ids = []
        for brep in result_breps:
            try:
                new_oid = doc.Objects.AddBrep(brep, attributes)
                new_ids.append(str(new_oid))
            except Exception:  # noqa: BLE001
                continue
        return new_ids

    def chunked_union(chunk_breps, tolerance, chunk_size=25, max_rounds=10):
        """Boolean-union many breps in small batches.

        A single ``CreateBooleanUnion`` over hundreds of boxes frequently
        returns ``None``; merging in chunks and repeating until no further
        reduction is much more robust.  Chunks that fail are kept untouched.
        """
        import System

        current = list(chunk_breps)
        rounds = 0
        while len(current) > 1 and rounds < max_rounds:
            rounds += 1
            count_before = len(current)
            next_round = []
            progress = False
            for start in range(0, len(current), chunk_size):
                chunk = current[start : start + chunk_size]
                if len(chunk) == 1:
                    next_round.append(chunk[0])
                    continue
                try:
                    brep_array = System.Array[Rhino.Geometry.Brep](chunk)
                    results = Rhino.Geometry.Brep.CreateBooleanUnion(brep_array, tolerance)
                except Exception as exc:  # noqa: BLE001
                    _debug_log("chunk union EXC: %r" % (exc,))
                    results = None
                if results:
                    results = list(results)
                    if len(results) < len(chunk):
                        next_round.extend(results)
                        progress = True
                    else:
                        next_round.extend(chunk)
                else:
                    next_round.extend(chunk)
            current = next_round
            if not progress:
                break
            _debug_log("union round %d: %d -> %d" % (rounds, count_before, len(current)))
        return current

    # Strategy 1: RhinoCommon, batched so hundreds of boxes merge reliably.
    new_ids = []
    try:
        merged = chunked_union(breps, 0.001)
        if len(merged) < len(breps):
            new_ids = add_results(merged)
            _debug_log("union chunked added %d" % len(new_ids))
    except Exception as exc:  # noqa: BLE001
        _debug_log("union chunked EXC: %r" % (exc,))
        new_ids = []
    # Strategy 2: rhinoscriptsyntax BooleanUnion (deletes inputs itself).
    if not new_ids:
        _debug_log("union fallback to rs.BooleanUnion")
        try:
            require_rs()
            guids = [str(oid) for oid in object_ids]
            result_guids = rs.BooleanUnion(guids)
            _debug_log("rs.BooleanUnion -> %r" % (result_guids,))
            if result_guids:
                new_ids = [str(guid) for guid in result_guids]
        except Exception as exc:  # noqa: BLE001
            _debug_log("rs.BooleanUnion EXC: %r" % (exc,))
            new_ids = []

    if not new_ids:
        return {
            "ok": False,
            "error_code": "execution_error",
            "error_message": "union failed; originals untouched",
        }

    # Delete originals only when a union path already replaced them.
    # Replace originals with the union result (union created new objects and did
    # not reuse input ids; rs fallback may already have deleted the inputs, in
    # which case Delete is a harmless no-op).
    if new_ids:
        for oid in object_ids:
            try:
                if str(oid) not in new_ids:
                    doc.Objects.Delete(oid, True)
            except Exception:  # noqa: BLE001
                pass
    return {
        "ok": True,
        "result": {
            "layer": layer,
            "before": len(breps),
            "after": len(new_ids),
            "unioned": len(new_ids) < len(breps),
            "object_ids": new_ids,
        },
    }


def runner(tool_name, arguments, dry_run):
    if tool_name == "rhino_scene_summary":
        return {"ok": True, "result": scene_summary(), "dry_run": False}
    if tool_name == "rhino_get_objects":
        return get_objects(arguments, dry_run)
    if tool_name == "rhino_create_box":
        return create_box(arguments, dry_run)
    if tool_name == "rhino_delete_object":
        return delete_object(arguments, dry_run)
    if tool_name == "rhino_union_layer":
        return union_layer(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": "unknown tool: %s" % tool_name}


def _rollback_log(message):
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


def rollback(rollback_token):
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


__all__ = [
    "TOOLS",
    "create_box",
    "delete_object",
    "get_objects",
    "require_rs",
    "rollback",
    "runner",
    "scene_summary",
    "snapshot",
    "union_layer",
]
