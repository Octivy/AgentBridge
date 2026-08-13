"""Headless Rhino host for the Host Adapter Contract v1.

Run inside Rhino's Python (EditPythonScript or startup script):

    import background_host
    background_host.main()

The package is self-contained: ``host.py`` / ``registration.py`` are bundled
copies, so it works from Rhino's scripts folder without the AgentBridge repo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import TOOLS, rollback, runner, snapshot  # noqa: E402
from host import HostAdapter, RhinoExecutor  # noqa: E402
from registration import write_registration  # noqa: E402


def main() -> None:
    # All Rhino document work must run on Rhino's main thread.  The executor
    # queues jobs and drains them from a WinForms timer / RhinoApp.Idle on the
    # thread that created it (the main thread when launched by the startup
    # script).  ``RhinoDoc.ActiveDoc`` is only reliable on the main thread, so
    # we never call the backend from the HTTP server thread directly.
    executor = RhinoExecutor(runner)
    executor.install_main_thread_timer()
    adapter = HostAdapter(
        host_id="rhino-main",
        host_kind="rhino",
        product="Rhino",
        product_version="1.0",
        tools=TOOLS,
        snapshot_fn=snapshot,
        execute_fn=executor.execute,
        rollback_fn=rollback,
    )
    adapter.start()
    write_registration(adapter.registration())
    print(f"AGENTBRIDGE_RHINO_HOST_READY {adapter.endpoint} {adapter.token}", flush=True)
    try:
        log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
        with open(log_path, "a") as handle:
            handle.write(
                "host main() returned; timer=%s idle=%s\n"
                % (executor.timer_installed, executor._idle_installed)
            )
    except Exception:
        pass
    # Deliberately no blocking loop: the HTTP server runs on a daemon thread
    # and the WinForms timer / Idle hook drains document work on the main
    # thread, so the startup script returns and Rhino stays responsive.


if __name__ == "__main__":
    main()
