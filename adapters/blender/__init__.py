"""Blender add-on: AgentBridge host adapter.

Install the folder as a Blender add-on, enable it, then run the
"AgentBridge: Start Host" operator (F3 search or the Render menu). The host
registers itself with the AgentBridge client and serves the contract endpoints
on 127.0.0.1. The actual bpy logic lives in ``backend.py`` and is shared with
the headless host (``background_host.py``).
"""

from __future__ import annotations

from typing import Any, Dict

try:
    import bpy  # noqa: F401
except ImportError:  # allow importing the package outside Blender for tests
    bpy = None

from .backend import TOOLS, rollback, runner, snapshot
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


if bpy is not None:

    class AGENTBRIDGE_OT_start_host(bpy.types.Operator):  # noqa: N801
        bl_idname = "agentbridge.start_host"
        bl_label = "AgentBridge: Start Host"

        def execute(self, context):
            del context
            if _STATE["adapter"] is not None:
                self.report({"INFO"}, "AgentBridge host is already running.")
                return {"CANCELLED"}
            executor = BlenderExecutor(runner)
            adapter = HostAdapter(
                host_id="blender-main",
                host_kind="blender",
                product="Blender",
                product_version=bpy.app.version_string,
                tools=TOOLS,
                snapshot_fn=snapshot,
                execute_fn=executor.execute,
                rollback_fn=rollback,
            )
            adapter.start()
            bpy.app.timers.register(executor.poll)
            write_registration(adapter.registration())
            _STATE["adapter"] = adapter
            _STATE["executor"] = executor
            _STATE["port"] = adapter.port
            self.report({"INFO"}, f"AgentBridge host listening on {adapter.endpoint}")
            return {"FINISHED"}

    class AGENTBRIDGE_OT_stop_host(bpy.types.Operator):  # noqa: N801
        bl_idname = "agentbridge.stop_host"
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
        self.layout.operator(AGENTBRIDGE_OT_start_host.bl_idname)
        self.layout.operator(AGENTBRIDGE_OT_stop_host.bl_idname)

    def register() -> None:
        bpy.utils.register_class(AGENTBRIDGE_OT_start_host)
        bpy.utils.register_class(AGENTBRIDGE_OT_stop_host)
        bpy.types.TOPBAR_MT_render.append(menu_func)

    def unregister() -> None:
        bpy.types.TOPBAR_MT_render.remove(menu_func)
        bpy.utils.unregister_class(AGENTBRIDGE_OT_stop_host)
        bpy.utils.unregister_class(AGENTBRIDGE_OT_start_host)
        if _STATE.get("adapter") is not None:
            AGENTBRIDGE_OT_stop_host.execute(AGENTBRIDGE_OT_stop_host, None)

else:

    def register() -> None:
        raise RuntimeError("AgentBridge Blender host requires bpy; run inside Blender.")

    def unregister() -> None:
        return


if __name__ == "__main__":
    register()
