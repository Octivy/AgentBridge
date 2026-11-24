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
    {
        "tool_name": "blender_create_primitive",
        "display_name": "创建几何体",
        "category": "modeling",
        "description": "预览并创建基础几何体（立方体/球/圆柱/圆锥），可回滚删除。",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["cube", "sphere", "cylinder", "cone"]},
                "name": {"type": "string"},
                "size": {"type": "number", "exclusiveMinimum": 0},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["kind"],
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
    {
        "tool_name": "blender_move_object",
        "display_name": "移动对象",
        "category": "modeling",
        "description": "预览并移动场景对象到新位置，可回滚恢复原位置。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["name", "location"],
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "medium",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
    {
        "tool_name": "blender_build_villa",
        "display_name": "建造欧式别墅",
        "category": "modeling",
        "description": "程序化生成一座两层欧式别墅（墙体、门窗、门廊、阳台、坡屋顶、烟囱、台阶、地面等），支持 dry-run 与回滚。",
        "input_schema": {
            "type": "object",
            "properties": {
                "width": {"type": "number", "exclusiveMinimum": 4},
                "depth": {"type": "number", "exclusiveMinimum": 4},
                "floor_height": {"type": "number", "exclusiveMinimum": 2},
            },
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
    {
        "tool_name": "blender_render_scene",
        "display_name": "渲染场景",
        "category": "analysis",
        "description": "将当前场景渲染为 PNG 图片（默认 Cycles CPU，无头环境稳定）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "width": {"type": "integer", "minimum": 64},
                "height": {"type": "integer", "minimum": 64},
                "engine": {"type": "string", "enum": ["cycles", "eevee", "workbench"]},
                "samples": {"type": "integer", "minimum": 1, "maximum": 4096},
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "medium",
        "result_schema": {"type": "object"},
        "rollback_supported": False,
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
    if tool_name == "blender_create_primitive":
        return create_primitive(arguments, dry_run)
    if tool_name == "blender_move_object":
        return move_object(arguments, dry_run)
    if tool_name == "blender_build_villa":
        return build_villa(arguments, dry_run)
    if tool_name == "blender_render_scene":
        return render_scene(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}


_PRIMITIVE_OPS = {
    "cube": "primitive_cube_add",
    "sphere": "primitive_uv_sphere_add",
    "cylinder": "primitive_cylinder_add",
    "cone": "primitive_cone_add",
}


def create_primitive(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    require_bpy()
    kind = str(arguments.get("kind") or "cube").strip().lower()
    if kind not in _PRIMITIVE_OPS:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": f"unknown primitive kind: {kind}"}
    size = float(arguments.get("size") or 2.0)
    location = [float(value) for value in (arguments.get("location") or [0, 0, 0])]
    name = str(arguments.get("name") or f"AgentBridge{kind.capitalize()}").strip()
    preview = {"kind": kind, "object_name": name, "size": size, "location": location}
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}

    op = getattr(bpy.ops.mesh, _PRIMITIVE_OPS[kind])
    if kind == "cube":
        op(size=size, location=location)
    elif kind == "sphere":
        op(radius=size / 2.0, location=location, segments=32, ring_count=16)
    elif kind == "cylinder":
        op(radius=size / 2.0, depth=size, location=location, vertices=32)
    else:
        op(radius1=size / 2.0, radius2=0.0, depth=size, location=location, vertices=32)
    obj = bpy.context.object
    obj.name = name
    return {
        "ok": True,
        "result": {"object_name": obj.name, "kind": kind, "size": size},
        "dry_run": False,
        "rollback_token": f"blender-primitive-{obj.name}",
    }


_ROLLBACK_LEDGER: Dict[str, tuple] = {}


def move_object(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    require_bpy()
    name = str(arguments.get("name") or "").strip()
    if not name:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "name is required"}
    location = [float(value) for value in (arguments.get("location") or [])]
    if len(location) != 3:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "location must contain 3 numbers"}

    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"ok": False, "error_code": "object_not_found", "error_message": f"object not found: {name}"}
    current = [round(value, 4) for value in obj.location]
    preview = {"object_name": name, "from": current, "to": location}
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}

    obj.location = location
    token = f"blender-move-{name}"
    _ROLLBACK_LEDGER[token] = ("move", {"name": name, "location": current})
    return {
        "ok": True,
        "result": {"object_name": name, "from": current, "to": [round(value, 4) for value in obj.location]},
        "dry_run": False,
        "rollback_token": token,
    }


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


VILLA_PREFIX = "Villa"


def _villa_material(name: str, color: tuple, *, roughness: float = 0.6, metallic: float = 0.0, transmission: float = 0.0) -> Any:
    require_bpy()
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = transmission
    return material


def _villa_box(name: str, dims: tuple, location: tuple, material: Any, parent: Any) -> Any:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    obj.scale = dims
    obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _villa_cylinder(name: str, radius: float, depth: float, location: tuple, material: Any, parent: Any, vertices: int = 16) -> Any:
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, vertices=vertices)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _villa_tri_prism(name: str, width: float, height: float, depth: float, location: tuple, material: Any, parent: Any) -> Any:
    import bmesh

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    half = width / 2.0
    verts = [
        bm.verts.new((-half, 0.0, 0.0)),
        bm.verts.new((half, 0.0, 0.0)),
        bm.verts.new((0.0, 0.0, height)),
        bm.verts.new((-half, depth, 0.0)),
        bm.verts.new((half, depth, 0.0)),
        bm.verts.new((0.0, depth, height)),
    ]
    specs = [
        ((0, 2, 1), "y"),
        ((4, 5, 3), "y-"),
        ((0, 1, 4, 3), "z-"),
        ((1, 2, 5, 4), "x"),
        ((2, 0, 3, 5), "x-"),
    ]
    for indices, outward in specs:
        face = bm.faces.new([verts[i] for i in indices])
        if outward == "y" and face.normal.y < 0:
            face.normal_flip()
        elif outward == "y-" and face.normal.y > 0:
            face.normal_flip()
        elif outward == "z-" and face.normal.z > 0:
            face.normal_flip()
        elif outward == "x" and face.normal.x < 0:
            face.normal_flip()
        elif outward == "x-" and face.normal.x > 0:
            face.normal_flip()
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _villa_hip_roof(name: str, base_width: float, base_depth: float, ridge: float, height: float, z_base: float, material: Any, parent: Any) -> Any:
    import bmesh

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    bw2 = base_width / 2.0
    bd2 = base_depth / 2.0
    r2 = ridge / 2.0
    verts = [
        bm.verts.new((-bw2, -bd2, z_base)),
        bm.verts.new((bw2, -bd2, z_base)),
        bm.verts.new((bw2, bd2, z_base)),
        bm.verts.new((-bw2, bd2, z_base)),
        bm.verts.new((-r2, 0.0, z_base + height)),
        bm.verts.new((r2, 0.0, z_base + height)),
    ]
    for indices in [
        (4, 5, 1, 0),
        (5, 4, 3, 2),
        (4, 0, 3),
        (5, 2, 1),
    ]:
        bm.faces.new([verts[i] for i in indices])
    bm.normal_update()
    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _villa_railing(name: str, start: tuple, end: tuple, base_z: float, height: float, material: Any, parent: Any, step: float = 0.25) -> None:
    import math

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    count = max(2, int(length / step))
    for i in range(count + 1):
        t = i / count
        x = start[0] + dx * t
        y = start[1] + dy * t
        _villa_cylinder(f"{name}.Baluster{i:02d}", 0.035, height, (x, y, base_z + height / 2.0), material, parent, vertices=10)
    if dx == 0:
        _villa_box(f"{name}.Rail", (0.08, length, 0.10), (start[0], start[1] + length / 2.0, base_z + height + 0.05), material, parent)
    else:
        _villa_box(f"{name}.Rail", (length, 0.08, 0.10), (start[0] + length / 2.0, start[1], base_z + height + 0.05), material, parent)


def _villa_window(name: str, x: float, y: float, z: float, axis: str, frame_mat: Any, glass_mat: Any, parent: Any) -> None:
    if axis == "y+":
        _villa_box(f"{name}.Frame", (1.5, 0.12, 1.7), (x, y + 0.05, z), frame_mat, parent)
        _villa_box(f"{name}.Glass", (1.2, 0.08, 1.4), (x, y + 0.13, z), glass_mat, parent)
    elif axis == "y-":
        _villa_box(f"{name}.Frame", (1.5, 0.12, 1.7), (x, y - 0.05, z), frame_mat, parent)
        _villa_box(f"{name}.Glass", (1.2, 0.08, 1.4), (x, y - 0.13, z), glass_mat, parent)
    elif axis == "x+":
        _villa_box(f"{name}.Frame", (0.12, 1.5, 1.7), (x + 0.05, y, z), frame_mat, parent)
        _villa_box(f"{name}.Glass", (0.08, 1.2, 1.4), (x + 0.13, y, z), glass_mat, parent)
    else:
        _villa_box(f"{name}.Frame", (0.12, 1.5, 1.7), (x - 0.05, y, z), frame_mat, parent)
        _villa_box(f"{name}.Glass", (0.08, 1.2, 1.4), (x - 0.13, y, z), glass_mat, parent)


def _delete_object(obj: Any) -> None:
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0 and mesh.name.startswith(VILLA_PREFIX + "."):
        bpy.data.meshes.remove(mesh)


def _remove_named_objects(root_name: str) -> list:
    removed = []
    prefix = f"{root_name}."
    for obj in list(bpy.data.objects):
        if obj.name == root_name or obj.name.startswith(prefix):
            _delete_object(obj)
            removed.append(obj.name)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0 and (mesh.name == root_name or mesh.name.startswith(prefix)):
            bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        if material.users == 0 and material.name.startswith(VILLA_PREFIX):
            bpy.data.materials.remove(material)
    return removed


def build_villa(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    require_bpy()
    import math
    from mathutils import Vector

    width = float(arguments.get("width") or 10.0)
    depth = float(arguments.get("depth") or 8.0)
    floor_height = float(arguments.get("floor_height") or 3.0)
    half_w = width / 2.0
    half_d = depth / 2.0

    preview = {
        "root_name": VILLA_PREFIX,
        "story": 2,
        "width": width,
        "depth": depth,
        "floor_height": floor_height,
        "features": [
            "foundation",
            "two floors of walls",
            "windows",
            "front door",
            "porch columns and pediment",
            "second-floor balcony",
            "hip roof",
            "chimney",
            "front steps",
            "ground plane",
        ],
        "materials": ["VillaWalls", "VillaTrim", "VillaRoof", "VillaGlass", "VillaWood", "VillaStone", "VillaBrick", "VillaGround"],
        "object_count_hint": "about 70 objects",
    }
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}

    removed_previous = _remove_named_objects(VILLA_PREFIX)
    cube = bpy.data.objects.get("Cube")
    if cube is not None and cube.type == "MESH":
        _delete_object(cube)

    root = bpy.data.objects.new(VILLA_PREFIX, None)
    bpy.context.collection.objects.link(root)
    root.empty_display_type = "SPHERE"

    walls_mat = _villa_material("VillaWalls", (0.86, 0.81, 0.68), roughness=0.8)
    trim_mat = _villa_material("VillaTrim", (0.96, 0.96, 0.93), roughness=0.5)
    roof_mat = _villa_material("VillaRoof", (0.68, 0.30, 0.16), roughness=0.9)
    glass_mat = _villa_material("VillaGlass", (0.04, 0.10, 0.16), roughness=0.12, metallic=0.4, transmission=0.3)
    wood_mat = _villa_material("VillaWood", (0.33, 0.21, 0.11), roughness=0.7)
    stone_mat = _villa_material("VillaStone", (0.72, 0.72, 0.74), roughness=0.9)
    brick_mat = _villa_material("VillaBrick", (0.62, 0.27, 0.20), roughness=0.9)
    ground_mat = _villa_material("VillaGround", (0.28, 0.46, 0.18), roughness=1.0)

    # ground plane and foundation
    _villa_box("Villa.Ground", (60.0, 60.0, 0.1), (0.0, 0.0, -0.05), ground_mat, root)
    _villa_box("Villa.Foundation", (width + 0.6, depth + 0.6, 0.35), (0.0, 0.0, 0.175), stone_mat, root)

    # two-story main volume and cornices
    _villa_box("Villa.Walls", (width, depth, floor_height * 2.0), (0.0, 0.0, floor_height), walls_mat, root)
    _villa_box("Villa.Cornice1F", (width + 0.6, depth + 0.6, 0.16), (0.0, 0.0, floor_height), trim_mat, root)
    _villa_box("Villa.Cornice2F", (width + 0.6, depth + 0.6, 0.16), (0.0, 0.0, floor_height * 2.0), trim_mat, root)

    # windows: front, back, and side walls
    for x in (-2.7, 2.7):
        _villa_window(f"Villa.Window.F1{x:+.1f}".replace("+", "").replace("-0.0", "0"), x, half_d, 1.6, "y+", trim_mat, glass_mat, root)
    for x in (-2.6, 0.0, 2.6):
        _villa_window(f"Villa.Window.F2{x:+.1f}".replace("+", "").replace("-0.0", "0"), x, half_d, 4.6, "y+", trim_mat, glass_mat, root)
    for x in (-2.5, 2.5):
        _villa_window(f"Villa.Window.B{x:+.1f}".replace("+", "").replace("-0.0", "0"), x, -half_d, 1.6, "y-", trim_mat, glass_mat, root)
        _villa_window(f"Villa.Window.B2{x:+.1f}".replace("+", "").replace("-0.0", "0"), x, -half_d, 4.6, "y-", trim_mat, glass_mat, root)
    for label, z in (("S1", 1.6), ("S2", 4.6)):
        _villa_window(f"Villa.Window.{label}L", -half_w, 0.0, z, "x-", trim_mat, glass_mat, root)
        _villa_window(f"Villa.Window.{label}R", half_w, 0.0, z, "x+", trim_mat, glass_mat, root)

    # front door, porch columns, pediment, steps
    _villa_box("Villa.DoorFrame", (1.9, 0.12, 2.6), (0.0, half_d + 0.03, 1.3), trim_mat, root)
    _villa_box("Villa.Door", (1.5, 0.14, 2.4), (0.0, half_d + 0.09, 1.2), wood_mat, root)
    _villa_box("Villa.DoorLintel", (2.2, 0.3, 0.18), (0.0, half_d + 0.03, 2.75), trim_mat, root)
    _villa_tri_prism("Villa.Pediment", 2.8, 0.65, 0.35, (0.0, half_d + 0.10, 2.92), trim_mat, root)
    for side in (-1.15, 1.15):
        _villa_box(f"Villa.ColumnBase{side:+.2f}".replace("+", ""), (0.34, 0.34, 0.12), (side, half_d + 0.30, 0.21), stone_mat, root)
        _villa_cylinder(f"Villa.Column{side:+.2f}".replace("+", ""), 0.11, 2.7, (side, half_d + 0.30, 1.5), trim_mat, root)
        _villa_box(f"Villa.ColumnCap{side:+.2f}".replace("+", ""), (0.38, 0.38, 0.14), (side, half_d + 0.30, 2.93), trim_mat, root)
    for i, (dims, y, z) in enumerate(
        [
            ((2.8, 0.45, 0.15), half_d + 0.55, 0.075),
            ((2.4, 0.45, 0.15), half_d + 1.0, 0.225),
            ((2.0, 0.45, 0.15), half_d + 1.45, 0.375),
        ]
    ):
        _villa_box(f"Villa.Step{i + 1}", dims, (0.0, y, z), stone_mat, root)

    # second-floor balcony with railing
    _villa_box("Villa.BalconySlab", (3.6, 1.4, 0.18), (0.0, half_d + 0.7, floor_height - 0.09), stone_mat, root)
    _villa_railing("Villa.BalconyFront", (-1.8, half_d + 1.4), (1.8, half_d + 1.4), floor_height, 1.0, trim_mat, root)
    _villa_railing("Villa.BalconyLeft", (-1.8, half_d), (-1.8, half_d + 1.4), floor_height, 1.0, trim_mat, root)
    _villa_railing("Villa.BalconyRight", (1.8, half_d), (1.8, half_d + 1.4), floor_height, 1.0, trim_mat, root)

    # hip roof and chimney
    _villa_hip_roof("Villa.Roof", width + 1.6, depth + 1.6, width - 2.6, 2.3, floor_height * 2.0, roof_mat, root)
    _villa_box("Villa.Chimney", (1.1, 1.1, 1.7), (2.6, -2.0, 7.9), brick_mat, root)
    _villa_box("Villa.ChimneyCap", (1.4, 1.4, 0.14), (2.6, -2.0, 8.82), brick_mat, root)

    # camera and sun
    camera = bpy.data.objects.get("Camera")
    if camera is None:
        bpy.ops.object.camera_add(location=(14.0, -11.0, 8.0))
        camera = bpy.context.object
    else:
        camera.location = (14.0, -11.0, 8.0)
    target = Vector((0.0, 0.0, 3.5))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()

    bpy.ops.object.light_add(type="SUN", location=(8.0, -9.0, 12.0))
    sun = bpy.context.object
    sun.name = "VillaSun"
    sun.rotation_euler = (math.radians(52), 0.0, math.radians(-38))
    sun.data.energy = 3.0

    world = bpy.data.worlds.get("World")
    if world is not None and world.use_nodes:
        background = world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs[0].default_value = (0.30, 0.42, 0.55, 1.0)
            background.inputs[1].default_value = 1.0

    created = [
        obj.name
        for obj in bpy.data.objects
        if obj.name == VILLA_PREFIX or obj.name.startswith(VILLA_PREFIX + ".")
    ]
    return {
        "ok": True,
        "result": {
            "object_name": VILLA_PREFIX,
            "object_count": len(created),
            "objects": created,
            "removed_previous": removed_previous,
        },
        "dry_run": False,
        "rollback_token": f"blender-villa-{VILLA_PREFIX}",
    }


def render_scene(arguments: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    require_bpy()
    import os

    filepath = str(arguments.get("filepath") or "").strip()
    if not filepath:
        return {"ok": False, "error_code": "invalid_arguments", "error_message": "filepath is required"}
    width = int(arguments.get("width") or 1280)
    height = int(arguments.get("height") or 720)
    engine = str(arguments.get("engine") or "cycles").strip().lower()
    samples = int(arguments.get("samples") or 32)
    absolute = os.path.abspath(filepath)

    preview = {
        "filepath": absolute,
        "width": width,
        "height": height,
        "samples": samples,
        "engine": engine,
        "format": "PNG",
    }
    if dry_run:
        return {"ok": True, "result": {"preview": preview}, "dry_run": True}

    directory = os.path.dirname(absolute)
    if directory:
        os.makedirs(directory, exist_ok=True)

    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = absolute
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        if hasattr(scene.cycles, "device"):
            scene.cycles.device = "CPU"
    elif engine == "eevee":
        engines = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
        for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            if candidate in engines:
                scene.render.engine = candidate
                break
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)
    return {
        "ok": True,
        "result": {**preview, "engine": scene.render.engine},
        "dry_run": False,
    }


def rollback(rollback_token: str) -> Dict[str, Any]:
    require_bpy()
    prefix = "blender-cube-"
    primitive_prefix = "blender-primitive-"
    villa_prefix = "blender-villa-"
    if rollback_token.startswith(villa_prefix):
        root_name = rollback_token[len(villa_prefix) :]
        removed = _remove_named_objects(root_name)
        return {"ok": True, "result": {"rolled_back": True, "object_name": root_name, "removed_objects": removed}}

    ledger_entry = _ROLLBACK_LEDGER.pop(rollback_token, None)
    if ledger_entry is not None:
        kind, payload = ledger_entry
        if kind == "move":
            obj = bpy.data.objects.get(payload["name"])
            if obj is None:
                return {"ok": True, "result": {"rolled_back": True, "already_absent": True}}
            obj.location = payload["location"]
            return {
                "ok": True,
                "result": {
                    "rolled_back": True,
                    "object_name": payload["name"],
                    "restored_location": payload["location"],
                },
            }

    for token_prefix in (primitive_prefix, prefix):
        if rollback_token.startswith(token_prefix):
            object_name = rollback_token[len(token_prefix) :]
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return {"ok": True, "result": {"rolled_back": True, "already_absent": True}}
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            return {"ok": True, "result": {"rolled_back": True, "object_name": object_name}}

    return {"ok": False, "error_code": "invalid_arguments", "error_message": "unknown rollback token"}


__all__ = [
    "TOOLS",
    "build_villa",
    "create_cube",
    "create_primitive",
    "move_object",
    "render_scene",
    "require_bpy",
    "rollback",
    "runner",
    "scene_summary",
    "snapshot",
]
