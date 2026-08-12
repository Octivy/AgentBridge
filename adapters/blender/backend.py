"""Blender ``bpy`` backend shared by the GUI add-on and the headless host.

``bpy`` is imported lazily so this module can be imported outside Blender
(unit tests). All functions assume they run on Blender's main thread.
"""

from __future__ import annotations

from typing import Any, Dict

try:
    import bpy
except ImportError:  # allow import outside Blender
    bpy = None


TOOLS = [
    {
        "tool_name": "blender_scene_summary",
        "display_name": "场景摘要",
        "category": "analysis",
        "description": "汇总当前 Blender 场景的对象、集合、活动对象与渲染帧。",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "dry_run_supported": False,
        "side_effect_level": "none",
        "result_schema": {"type": "object"},
    },
    {
        "tool_name": "blender_create_cube",
        "display_name": "创建立方体",
        "category": "modeling",
        "description": "预览并创建一个立方体网格对象，可回滚删除。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "size": {"type": "number", "exclusiveMinimum": 0},
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


def require_bpy() -> None:
    if bpy is None:
        raise RuntimeError("bpy is required; run inside Blender")


def scene_summary() -> Dict[str, Any]:
    require_bpy()
    scene = bpy.context.scene
    objects = []
    for obj in scene.objects:
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "location": [round(value, 4) for value in obj.location],
                "visible": obj.visible_get(),
            }
        )
    active = ""
    view_layer = getattr(bpy.context, "view_layer", None)
    if view_layer is not None and view_layer.objects.active is not None:
        active = view_layer.objects.active.name
    return {
        "schema_version": 1,
        "source": "blender",
        "scene": {"name": scene.name, "frame": scene.frame_current},
        "object_count": len(objects),
        "objects": objects,
        "active_object": active,
    }


def snapshot(scope: Dict[str, Any]) -> Dict[str, Any]:
    del scope
    return {"ok": True, "snapshot": scene_summary()}


def runner(tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if tool_name == "blender_scene_summary":
        return {"ok": True, "result": scene_summary(), "dry_run": False}
    if tool_name == "blender_create_cube":
        return create_cube(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}


def create_cube(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    require_bpy()
    size = float(arguments.get("size") or 2.0)
    location = [float(value) for value in (arguments.get("location") or [0, 0, 0])]
    name = str(arguments.get("name") or "AgentBridgeCube").strip()
    preview = {
        "object_name": name,
        "mesh_name": f"{name}Mesh",
        "verts": 8,
        "edges": 12,
        "faces": 6,
        "size": size,
        "location": location,
    }
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    cube = bpy.context.object
    cube.name = name
    return {
        "ok": True,
        "result": {"object_name": cube.name, "mesh_name": cube.data.name, "verts": 8, "faces": 6},
        "dry_run": False,
        "rollback_token": f"blender-cube-{cube.name}",
    }


def rollback(rollback_token: str) -> Dict[str, Any]:
    require_bpy()
    prefix = "blender-cube-"
    if not rollback_token.startswith(prefix):
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback token"}
    object_name = rollback_token[len(prefix) :]
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return {"ok": True, "result": {"rolled_back": True, "already_absent": True}}
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    return {"ok": True, "result": {"rolled_back": True, "object_name": object_name}}


__all__ = ["TOOLS", "create_cube", "require_bpy", "rollback", "runner", "scene_summary", "snapshot"]
