"""Detect supported software installed on this machine.

The connector's first-run experience depends on answering "what can we connect
to?" without asking the user to type host ids or paths. Detection combines the
Windows registry (uninstall keys, app paths) with well-known install/user-data
locations. Every probe is read-only and must never raise: any failure simply
means "not detected".
"""

from __future__ import annotations

import os
import winreg
from pathlib import Path
from typing import Dict, List, Optional

from adapter_install.blender import blender_user_root, detect_blender_versions
from adapter_install.rhino import detect_rhino_versions, rhino_user_root
from adapter_install.sketchup import detect_sketchup_versions

SUPPORTED_SOFTWARE = ("blender", "sketchup", "rhino", "autocad")

_REGISTRY_UNINSTALL_ROOTS = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _read_registry_string(root: int, subkey: str, value: str) -> str:
    try:
        with winreg.OpenKey(root, subkey) as key:
            data, _ = winreg.QueryValueEx(key, value)
            return str(data or "").strip()
    except OSError:
        return ""


def _registry_value_from_roots(subkey: str, value: str) -> str:
    for root, base in _REGISTRY_UNINSTALL_ROOTS[:1] + (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
    ):
        candidate = subkey if base.endswith("Uninstall") else base + "\\" + subkey
        text = _read_registry_string(root, candidate, value)
        if text:
            return text
    return ""


def _scan_uninstall_display_names(fragment: str) -> str:
    """Return the first DisplayName containing ``fragment`` (case-insensitive)."""

    needle = fragment.strip().lower()
    if not needle:
        return ""
    for root, base in _REGISTRY_UNINSTALL_ROOTS:
        try:
            with winreg.OpenKey(root, base) as parent:
                count, _, _ = winreg.QueryInfoKey(parent)
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(parent, index)
                        display = _read_registry_string(root, base + "\\" + subkey_name, "DisplayName")
                    except OSError:
                        continue
                    if display and needle in display.lower():
                        return display
        except OSError:
            continue
    return ""


def _existing_dirs(candidates: List[Path]) -> List[str]:
    found: List[str] = []
    for candidate in candidates:
        try:
            if candidate.is_dir():
                found.append(str(candidate))
        except OSError:
            continue
    return found


def _existing_files(candidates: List[Path]) -> List[str]:
    found: List[str] = []
    for candidate in candidates:
        try:
            if candidate.is_file():
                found.append(str(candidate))
        except OSError:
            continue
    return found


def detect_blender_installations() -> List[Dict[str, str]]:
    installs: List[Dict[str, str]] = []
    for version in detect_blender_versions():
        installs.append(
            {
                "version": version,
                "source": "user-data",
                "install_path": str(blender_user_root() / version),
            }
        )
    display = _scan_uninstall_display_names("blender")
    if display and not any(item["source"] == "registry" for item in installs):
        installs.append({"version": display, "source": "registry", "install_path": ""})
    return installs


def detect_sketchup_installations() -> List[Dict[str, str]]:
    installs: List[Dict[str, str]] = []
    for version in detect_sketchup_versions():
        installs.append({"version": version, "source": "user-data", "install_path": ""})
    display = _scan_uninstall_display_names("sketchup")
    if display and not installs:
        installs.append({"version": display, "source": "registry", "install_path": ""})
    return installs


def detect_rhino_installations() -> List[Dict[str, str]]:
    installs: List[Dict[str, str]] = []
    for version in detect_rhino_versions():
        installs.append({"version": version, "source": "user-data", "install_path": str(rhino_user_root() / version)})
    program_files = os.getenv("ProgramFiles") or r"C:\Program Files"
    for path in _existing_dirs([Path(program_files) / "Rhino 8", Path(program_files) / "Rhino 7"]):
        installs.append({"version": Path(path).name, "source": "install-dir", "install_path": path})
    return installs


def detect_autocad_installations() -> List[Dict[str, str]]:
    installs: List[Dict[str, str]] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Autodesk\AutoCAD") as key:
            count, _, _ = winreg.QueryInfoKey(key)
            for index in range(count):
                try:
                    release = winreg.EnumKey(key, index)
                except OSError:
                    continue
                install = _registry_value_from_roots("Autodesk\\AutoCAD\\" + release, "Location")
                installs.append(
                    {
                        "version": release,
                        "source": "registry",
                        "install_path": install,
                    }
                )
    except OSError:
        pass
    if not installs:
        display = _scan_uninstall_display_names("autocad")
        if display:
            installs.append({"version": display, "source": "registry", "install_path": ""})
    return installs


def autocad_plugin_status() -> Dict[str, object]:
    """Whether the AgentBridge AutoCAD bundle is installed (auto-loads on launch)."""

    base = os.getenv("APPDATA") or str(Path.home())
    bundle = Path(base) / "Autodesk" / "ApplicationPlugins" / "AgentBridge.bundle"
    try:
        return {
            "installed": bundle.is_dir(),
            "path": str(bundle),
            "note": "插件随 AutoCAD 启动自动加载" if bundle.is_dir() else "尚未安装自动加载插件包",
        }
    except OSError:
        return {"installed": False, "path": str(bundle), "note": "检测失败"}


_DETECTORS = {
    "blender": detect_blender_installations,
    "sketchup": detect_sketchup_installations,
    "rhino": detect_rhino_installations,
    "autocad": detect_autocad_installations,
}

# 进程名 -> host_kind，用于"是否正在运行"状态展示。
_EXECUTABLE_KINDS = {
    "blender.exe": "blender",
    "blender-launcher.exe": "blender",
    "sketchup.exe": "sketchup",
    "rhino.exe": "rhino",
    "acad.exe": "autocad",
}


def _running_process_names() -> set:
    """Enumerate running process image names via Windows API (no pipes)."""

    names = set()
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        process_ids = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not kernel32.K32EnumProcesses(ctypes.byref(process_ids), ctypes.sizeof(process_ids), ctypes.byref(needed)):
            return names
        count = needed.value // ctypes.sizeof(wintypes.DWORD)
        for index in range(count):
            pid = process_ids[index]
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                continue
            try:
                buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if psapi.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    names.add(buffer.value.rsplit("\\", 1)[-1].lower())
            finally:
                kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - status display must never crash
        return set()
    return names


def detect_running_software(kinds: Optional[List[str]] = None) -> Dict[str, bool]:
    """Map host_kind -> whether the software process is currently running."""

    names = _running_process_names()
    wanted = set(kinds or SUPPORTED_SOFTWARE)
    result: Dict[str, bool] = {}
    for exe, kind in _EXECUTABLE_KINDS.items():
        if kind in wanted and kind not in result:
            result[kind] = exe in names
    return result


def detect_installed_software(
    kinds: Optional[List[str]] = None,
    *,
    adapter_status: Optional[Dict[str, Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """Detect supported software on this machine.

    ``adapter_status`` maps host_kind -> {"installed": bool, ...} and is merged
    into each result so callers can render "可连接 / 已装插件" badges.
    """

    status_map = adapter_status or {}
    results: List[Dict[str, object]] = []
    for kind in kinds or SUPPORTED_SOFTWARE:
        detector = _DETECTORS.get(kind)
        if detector is None:
            continue
        try:
            installations = detector()
        except Exception:  # noqa: BLE001 - detection must never break the panel
            installations = []
        adapter = status_map.get(kind) or {}
        results.append(
            {
                "host_kind": kind,
                "detected": bool(installations),
                "installations": installations,
                "adapter_installed": bool(adapter.get("installed")),
                "adapter_detail": adapter,
            }
        )
    return results


__all__ = [
    "SUPPORTED_SOFTWARE",
    "autocad_plugin_status",
    "detect_autocad_installations",
    "detect_blender_installations",
    "detect_installed_software",
    "detect_rhino_installations",
    "detect_running_software",
    "detect_sketchup_installations",
]
