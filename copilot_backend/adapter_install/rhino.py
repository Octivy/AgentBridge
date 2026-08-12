"""One-click Rhino adapter install (prepared; launch wiring verified after Rhino reinstall).

Rhino 8 runs Python from %APPDATA%\\McNeel\\Rhinoceros\\<ver>\\scripts. This
installer copies the AgentBridge Rhino adapter there as an importable package
and writes a startup script that imports it and starts the host (with logging,
so the exact startup hook can be verified/fixed on the target machine).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List


PACKAGE_NAME = "agentbridge_rhino"
STARTUP_NAME = "AgentBridgeHost_startup.py"

STARTUP_SCRIPT = '''# AgentBridge Rhino host startup (diagnostic logging included).
import os
import sys
import traceback

LOG_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
_HERE = os.path.dirname(os.path.abspath(__file__))


def _log(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(message + "\\n")
    except Exception:
        pass


_log("AgentBridge Rhino startup running")
try:
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import agentbridge_rhino.background_host as host

    host.main()
    _log("host started")
except Exception:
    _log("ERROR: " + traceback.format_exc())
'''


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def rhino_user_root() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "McNeel" / "Rhinoceros"


def detect_rhino_versions(root: Path | None = None) -> List[str]:
    base = root or rhino_user_root()
    if not base.is_dir():
        return []
    versions: List[str] = []
    for entry in base.glob("*"):
        if entry.is_dir() and entry.name.strip():
            versions.append(entry.name.strip())
    return sorted(versions, reverse=True)


def package_target_dir(version: str, root: Path | None = None) -> Path:
    base = root or rhino_user_root()
    return base / version / "scripts" / PACKAGE_NAME


def startup_target_path(version: str, root: Path | None = None) -> Path:
    base = root or rhino_user_root()
    return base / version / "scripts" / STARTUP_NAME


def install_rhino_adapter(
    root: Path | None = None,
    repo_root: Path | None = None,
) -> Dict[str, object]:
    versions = detect_rhino_versions(root)
    if not versions:
        return {
            "ok": False,
            "installed": [],
            "rhino_versions": [],
            "message": "未检测到 Rhino（%APPDATA%\\McNeel\\Rhinoceros\\*）",
        }
    source = (repo_root or _repo_root()) / "adapters" / "rhino"
    installed: List[str] = []
    for version in versions:
        target = package_target_dir(version, root)
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
        "rhino_versions": versions,
        "message": "已安装 Rhino 适配器，请重装/重启 Rhino 后验证自动启动（详见 rhino-startup.log）",
    }


def rhino_adapter_status(root: Path | None = None) -> Dict[str, object]:
    versions = detect_rhino_versions(root)
    results: List[Dict[str, object]] = []
    for version in versions:
        package = package_target_dir(version, root)
        startup = startup_target_path(version, root)
        results.append(
            {
                "version": version,
                "installed": (package / "backend.py").exists(),
                "autostart": startup.exists(),
                "path": str(package),
            }
        )
    return {
        "ok": True,
        "rhino_versions": versions,
        "adapters": results,
    }


__all__ = [
    "PACKAGE_NAME",
    "STARTUP_NAME",
    "detect_rhino_versions",
    "install_rhino_adapter",
    "package_target_dir",
    "rhino_adapter_status",
    "startup_target_path",
]
