"""Headless Blender host for the Host Adapter Contract v1.

Usage:

    blender --background --python adapters/blender/background_host.py

The HTTP server runs in a background thread; bpy operations are executed on
Blender's main thread through a queue polled by this script's main loop.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy  # noqa: E402  (only exists inside Blender)

from adapters.blender.backend import TOOLS, rollback, runner, snapshot  # noqa: E402
from adapters.blender.host import BlenderExecutor, HostAdapter  # noqa: E402
from adapters.blender.registration import write_registration  # noqa: E402


def main() -> None:
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
    write_registration(adapter.registration())
    print(f"AGENTBRIDGE_BLENDER_HOST_READY {adapter.endpoint} {adapter.token}", flush=True)
    while True:
        executor.poll()
        time.sleep(0.05)


if __name__ == "__main__":
    main()
