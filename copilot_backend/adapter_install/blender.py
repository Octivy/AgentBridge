"""One-click Blender add-on install.

The AgentBridge Blender add-on (adapters/blender) exposes the live scene of a
visible Blender instance to the client. This installer copies the add-on into
Blender's user addons folder and adds a startup script that auto-enables it and
starts the host, so opening Blender is enough to connect.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List


ADDON_NAME = "agentbridge_host"
STARTUP_NAME = "agentbridge_host_autostart.py"

STARTUP_SCRIPT = """# AgentBridge: auto-enable host addon and start the bridge.
import os
import sys
import traceback

LOG_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "blender-startup.log")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ADDONS = os.path.join(os.path.dirname(_HERE), "addons")


def _log(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(message + "\\n")
    except Exception:
        pass


_log("AgentBridge startup script running")
try:
    import bpy

    if _ADDONS not in sys.path:
        sys.path.insert(0, _ADDONS)
    _log("importing addon from " + _ADDONS)
    import agentbridge_host

    agentbridge_host.register()
    _log("addon registered")
    _log("starting host")
    bpy.ops.agentbridge.start_host()
    _log("host started")
except Exception:
    _log("ERROR: " + traceback.format_exc())
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def blender_user_root() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "Blender Foundation" / "Blender"


def detect_blender_versions(root: Path | None = None) -> List[str]:
    """Return detected Blender version folders, newest first (e.g. '5.1')."""

    base = root or blender_user_root()
    if not base.is_dir():
        return []
    versions: List[str] = []
    for entry in base.glob("*"):
        if entry.is_dir() and entry.name.strip():
            versions.append(entry.name.strip())
    return sorted(versions, reverse=True)


def addon_target_dir(version: str, root: Path | None = None) -> Path:
    base = root or blender_user_root()
    return base / version / "scripts" / "addons" / ADDON_NAME


def startup_target_path(version: str, root: Path | None = None) -> Path:
    base = root or blender_user_root()
    return base / version / "scripts" / "startup" / STARTUP_NAME


def install_blender_addon(
    root: Path | None = None,
    repo_root: Path | None = None,
) -> Dict[str, object]:
    versions = detect_blender_versions(root)
    if not versions:
        return {
            "ok": False,
            "installed": [],
            "blender_versions": [],
            "message": "未检测到 Blender（%APPDATA%\\Blender Foundation\\Blender\\*）",
        }
    source = (repo_root or _repo_root()) / "adapters" / "blender"
    installed: List[str] = []
    for version in versions:
        target = addon_target_dir(version, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        startup = startup_target_path(version, root)
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup.write_text(STARTUP_SCRIPT, encoding="utf-8")
        installed.append(str(target))
    return {
        "ok": True,
        "installed": installed,
        "blender_versions": versions,
        "message": "已安装 Blender 插件，重新打开 Blender 即自动连接",
    }


def blender_addon_status(root: Path | None = None) -> Dict[str, object]:
    versions = detect_blender_versions(root)
    results: List[Dict[str, object]] = []
    for version in versions:
        addon = addon_target_dir(version, root)
        startup = startup_target_path(version, root)
        results.append(
            {
                "version": version,
                "installed": (addon / "__init__.py").exists(),
                "autostart": startup.exists(),
                "path": str(addon),
            }
        )
    return {
        "ok": True,
        "blender_versions": versions,
        "addons": results,
    }


__all__ = [
    "ADDON_NAME",
    "STARTUP_NAME",
    "addon_target_dir",
    "blender_addon_status",
    "detect_blender_versions",
    "install_blender_addon",
    "startup_target_path",
]
