"""Blender add-on: AgentBridge host adapter.

Install the folder as a Blender add-on, enable it, then run the
"AgentBridge: Start Host" operator (F3 search or the Render menu). The host
registers itself with the AgentBridge client and serves the contract endpoints
on 127.0.0.1.
"""

from __future__ import annotations

from typing import Any, Dict

try:
    import bpy  # noqa: F401
except ImportError:  # allow importing the package outside Blender for tests
    bpy = None

from .host import BlenderExecutor, HostAdapter
from .registration import remove_registration, write_registration


bl_info = {
    "name": "AgentBridge Host",
    "author": "AgentBridge",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "Render > AgentBridge",
    "description": "Expose Blender to the AgentBridge client over a local host adapter.",
    "category": "Development",
}


_STATE: Dict[str, Any] = {"adapter": None, "executor": None, "port": 0}


def _scene_summary() -> Dict[str, Any]:
    scene = bpy.context.scene
    objects = []
    for obj in scene.objects:
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "location": [round(v, 4) for v in obj.location],
                "visible": obj.visible_get(),
            }
        )
    return {
        "schema_version": 1,
        "source": "blender",
        "scene": {"name": scene.name, "frame": scene.frame_current},
        "object_count": len(objects),
        "objects": objects,
        "active_object": scene.objects.active.name if scene.objects.active else "",
    }


def _snapshot(scope: Dict[str, Any]) -> Dict[str, Any]:
    del scope
    return {"ok": True, "snapshot": _scene_summary()}


def _runner(tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if tool_name == "blender_scene_summary":
        return {"ok": True, "result": _scene_summary(), "dry_run": False}
    if tool_name == "blender_create_cube":
        return _create_cube(arguments, dry_run)
    return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}


def _create_cube(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    size = float(arguments.get("size") or 2.0)
    location = [float(v) for v in (arguments.get("location") or [0, 0, 0])]
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


def _rollback(rollback_token: str) -> Dict[str, Any]:
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


if bpy is not None:

    class CADCOPILOT_OT_start_host(bpy.types.Operator):  # noqa: N801
        bl_idname = "cadcopilot.start_host"
        bl_label = "AgentBridge: Start Host"

        def execute(self, context):
            del context
            if _STATE["adapter"] is not None:
                self.report({"INFO"}, "AgentBridge host is already running.")
                return {"CANCELLED"}
            executor = BlenderExecutor(_runner)
            adapter = HostAdapter(
                host_id="blender-main",
                host_kind="blender",
                product="Blender",
                product_version=bpy.app.version_string,
                tools=TOOLS,
                snapshot_fn=_snapshot,
                execute_fn=executor.execute,
                rollback_fn=_rollback,
            )
            adapter.start()
            bpy.app.timers.register(executor.poll)
            write_registration(adapter.registration())
            _STATE["adapter"] = adapter
            _STATE["executor"] = executor
            _STATE["port"] = adapter.port
            self.report({"INFO"}, f"AgentBridge host listening on {adapter.endpoint}")
            return {"FINISHED"}

    class CADCOPILOT_OT_stop_host(bpy.types.Operator):  # noqa: N801
        bl_idname = "cadcopilot.stop_host"
        bl_label = "AgentBridge: Stop Host"

        def execute(self, context):
            del context
            adapter = _STATE.get("adapter")
            executor = _STATE.get("executor")
            if adapter is not None:
                adapter.stop()
                if executor is not None:
                    bpy.app.timers.unregister(executor.poll)
                remove_registration("blender-main")
            _STATE["adapter"] = None
            _STATE["executor"] = None
            self.report({"INFO"}, "AgentBridge host stopped.")
            return {"FINISHED"}

    def menu_func(self, context):
        del context
        self.layout.operator(CADCOPILOT_OT_start_host.bl_idname)
        self.layout.operator(CADCOPILOT_OT_stop_host.bl_idname)

    def register() -> None:
        bpy.utils.register_class(CADCOPILOT_OT_start_host)
        bpy.utils.register_class(CADCOPILOT_OT_stop_host)
        bpy.types.TOPBAR_MT_render.append(menu_func)

    def unregister() -> None:
        bpy.types.TOPBAR_MT_render.remove(menu_func)
        bpy.utils.unregister_class(CADCOPILOT_OT_stop_host)
        bpy.utils.unregister_class(CADCOPILOT_OT_start_host)
        if _STATE.get("adapter") is not None:
            CADCOPILOT_OT_stop_host.execute(CADCOPILOT_OT_stop_host, None)

else:

    def register() -> None:
        raise RuntimeError("AgentBridge Blender host requires bpy; run inside Blender.")

    def unregister() -> None:
        return


if __name__ == "__main__":
    register()
