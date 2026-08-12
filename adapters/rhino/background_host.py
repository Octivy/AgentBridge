"""Headless Rhino host for the Host Adapter Contract v1.

Run inside Rhino's Python (EditPythonScript or startup script):

    import background_host
    background_host.main()
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.blender.host import HostAdapter  # noqa: E402  (stdlib generic host)
from adapters.rhino.backend import TOOLS, rollback, runner, snapshot  # noqa: E402


def main() -> None:
    adapter = HostAdapter(
        host_id="rhino-main",
        host_kind="rhino",
        product="Rhino",
        product_version="1.0",
        tools=TOOLS,
        snapshot_fn=snapshot,
        execute_fn=runner,
        rollback_fn=rollback,
    )
    adapter.start()
    from adapters._shared.registration import write_registration

    write_registration(adapter.registration())
    print(f"AGENTBRIDGE_RHINO_HOST_READY {adapter.endpoint} {adapter.token}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.stop()


if __name__ == "__main__":
    main()
