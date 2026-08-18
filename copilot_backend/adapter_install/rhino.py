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

STARTUP_SCRIPT = '''#! python 3
# AgentBridge Rhino host startup (diagnostic logging included).
# Compatible with Python 2.7 (Rhino 6 / IronPython) and Python 3 (Rhino 7+).
import io
import os
import json
import sys
import traceback

try:
    import urllib.request as _urllib_request  # Python 3
except ImportError:
    import urllib2 as _urllib_request  # Python 2.7

LOG_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")

# Rhino stages scripts under ~/.rhinocode/stage before running them, so
# __file__ does NOT point at the real scripts folder. Resolve the package from
# the canonical Rhino scripts directory instead.
_SCRIPTS_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "McNeel", "Rhinoceros", "__RHINO_VERSION__", "scripts",
)
_REGISTRY_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "hosts")


def _ensure_dir(path):
    try:
        os.makedirs(path)
    except OSError:
        pass


def _log(message):
    try:
        import datetime
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _ensure_dir(os.path.dirname(LOG_PATH))
        with io.open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write("[" + stamp + "] " + message + "\\n")
    except Exception:
        pass


def _http_status(url, token, timeout):
    req = _urllib_request.Request(url, headers={"x-cadcopilot-token": token})
    try:
        # Bypass the system proxy: on this machine a local proxy (clash/v2ray)
        # intercepts 127.0.0.1 and makes the health probe return 502.
        _opener = _urllib_request.build_opener(_urllib_request.ProxyHandler({}))
        resp = _opener.open(req, timeout=timeout)
    except Exception:
        return None
    try:
        code = resp.getcode()
    except Exception:
        code = None
    try:
        resp.close()
    except Exception:
        pass
    return code


_log("AgentBridge Rhino startup running")
_py_pid = str(os.getpid())
_rhino_pid = None
try:
    import System.Diagnostics as _diag
    _rhino_pid = str(_diag.Process.GetCurrentProcess().Id)
except Exception:
    pass
_log("pids: rhino=%s python=%s" % (_rhino_pid, _py_pid))
if _rhino_pid and _py_pid != _rhino_pid:
    _log("WARNING: script runs in a SEPARATE process (RhinoCode editor?). "
         "The host thread dies when this process exits. Run it from Rhino's "
         "command bar instead: _-RunPythonScript <path to this file>")
try:
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)

    # Idempotent startup: if a live host is already registered for this Rhino
    # process, do not start a second one (a second host freezes Rhino). If a
    # registration for THIS process exists but the endpoint refuses connections
    # (e.g. the adapter thread died), remove it and start fresh.
    _alive = False
    _pid = _rhino_pid
    if os.path.isdir(_REGISTRY_DIR):
        for _name in os.listdir(_REGISTRY_DIR):
            if not _name.startswith("rhino-main-"):
                continue
            try:
                with io.open(os.path.join(_REGISTRY_DIR, _name), "r", encoding="utf-8") as _fh:
                    _reg = json.load(_fh)
                if not _pid or str(_reg.get("pid")) != _pid:
                    continue
                _code = _http_status(
                    _reg["endpoint"].rstrip("/") + "/health",
                    _reg.get("token", ""),
                    1,
                )
                if _code == 200:
                    _alive = True
                    _log("host already running; skipping duplicate startup")
                    break
                _log("stale registration for this process; removing " + _name)
                try:
                    os.remove(os.path.join(_REGISTRY_DIR, _name))
                except Exception:
                    pass
            except Exception:
                continue

    # Re-import the host package. Rhino caches modules in sys.modules for the
    # whole session, and the adapter is imported both as "agentbridge_rhino.*"
    # and as top-level "backend"/"host"/"registration", so purge anything
    # whose source lives under the agentbridge_rhino folder.
    for _mod_name in list(sys.modules):
        _mod = sys.modules.get(_mod_name)
        try:
            _src = str(getattr(_mod, "__file__", "") or "")
        except Exception:
            _src = ""
        if "agentbridge_rhino" in _src:
            del sys.modules[_mod_name]
    import agentbridge_rhino.background_host as host

    if not _alive:
        host.main()
        _log("host started")
        # Post-start self-check: confirm the HTTP endpoint actually answers.
        # Rhino 8's RhinoCode stages scripts and may unload the runtime when the
        # startup command finishes, silently killing the host; surface that here
        # instead of leaving a dead registration behind.
        try:
            import time as _time

            _time.sleep(1.5)
            _ok = False
            if os.path.isdir(_REGISTRY_DIR):
                for _name in os.listdir(_REGISTRY_DIR):
                    if not _name.startswith("rhino-main-"):
                        continue
                    try:
                        with io.open(os.path.join(_REGISTRY_DIR, _name), "r", encoding="utf-8") as _fh:
                            _reg = json.load(_fh)
                        if _pid and str(_reg.get("pid")) != _pid:
                            continue
                        _code = _http_status(
                            _reg["endpoint"].rstrip("/") + "/health",
                            _reg.get("token", ""),
                            2,
                        )
                        if _code == 200:
                            _ok = True
                            break
                    except Exception:
                        continue
            if _ok:
                _log("self-check ok: endpoint answering")
            else:
                _log("SELF-CHECK FAILED: host started but endpoint not answering; "
                     "Rhino may have unloaded the script engine")
        except Exception:
            _log("self-check error: " + traceback.format_exc())
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
        startup.write_text(STARTUP_SCRIPT.replace("__RHINO_VERSION__", version), encoding="utf-8")
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
