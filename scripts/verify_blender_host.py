"""Real Blender end-to-end verification for the host adapter.

Launches Blender in background mode with the headless host adapter, discovers
it through the registry, then verifies: manifest, health, snapshot, write
dry-run, authorized commit and rollback against a real Blender scene.

Usage:

    python scripts/verify_blender_host.py

Blender is located via ``BLENDER_EXE`` or common install paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copilot_backend"))

from host_runtime.client import HostClient  # noqa: E402
from host_runtime.registry import list_registrations  # noqa: E402


def find_blender() -> str:
    configured = os.getenv("BLENDER_EXE", "").strip()
    if configured and Path(configured).is_file():
        return configured
    candidates = [
        Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
        Path(r"D:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
        Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
        Path(r"D:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("Blender not found; set BLENDER_EXE to the blender.exe path.")


def wait_for_host(registry_dir: Path, timeout_seconds: float = 90.0):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for registration in list_registrations(registry_dir):
            if registration.host_id == "blender-main":
                return registration
        time.sleep(1.0)
    raise TimeoutError("blender host did not register within the timeout")


def main() -> int:
    blender = find_blender()
    background_script = ROOT / "adapters" / "blender" / "background_host.py"
    with tempfile.TemporaryDirectory(prefix="agentbridge-blender-") as tmp:
        registry_dir = Path(tmp) / "AgentBridge" / "hosts"
        env = dict(os.environ)
        env["LOCALAPPDATA"] = tmp
        process = subprocess.Popen(
            [blender, "--background", "--python", str(background_script)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            registration = wait_for_host(registry_dir)
            client = HostClient(registration.endpoint, registration.token, timeout_seconds=20)

            manifest = client.manifest()
            tool_names = [tool["tool_name"] for tool in manifest["tools"]]
            assert tool_names == ["blender_scene_summary", "blender_create_cube"], tool_names

            health = client.health()
            assert health["ok"] is True and health["product"] == "Blender"

            snapshot = client.snapshot({})
            assert snapshot["snapshot"]["source"] == "blender"
            initial_count = snapshot["snapshot"]["object_count"]

            preview = client.execute_tool(
                "blender_create_cube",
                {"name": "ABVerify", "size": 1.0},
                dry_run=True,
            )
            assert preview["ok"] is True and preview["dry_run"] is True

            commit = client.execute_tool(
                "blender_create_cube",
                {"name": "ABVerify", "size": 1.0, "permission_request_id": "verify-perm-1"},
                dry_run=False,
            )
            assert commit["ok"] is True
            assert commit["result"]["object_name"] == "ABVerify"
            rollback_token = commit.get("rollback_token")
            assert rollback_token

            after_create = client.snapshot({})
            assert after_create["snapshot"]["object_count"] == initial_count + 1

            rolled_back = client.rollback(rollback_token)
            assert rolled_back["ok"] is True
            assert rolled_back["result"]["rolled_back"] is True

            after_rollback = client.snapshot({})
            assert after_rollback["snapshot"]["object_count"] == initial_count

            print("BLENDER HOST VERIFICATION PASSED")
            print(f"blender={health['product_version']} endpoint={registration.endpoint}")
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
