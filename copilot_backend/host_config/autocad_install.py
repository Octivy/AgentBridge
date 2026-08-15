"""Build and install the AutoCAD plugin bundle (one-click from the panel).

The plugin is an Autodesk application bundle that must live under
%APPDATA%\\Autodesk\\ApplicationPlugins\\AgentBridge.bundle; AutoCAD loads it
automatically at startup. This module runs the repo's build script and copies
the produced bundle there, so users never need PowerShell.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_and_install_autocad_plugin(autocad_version: str = "2016") -> Dict[str, Any]:
    root = _repo_root()
    script = root / "scripts" / "build-plugin-package.ps1"
    if not script.exists():
        raise RuntimeError(f"构建脚本不存在：{script}")

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-AutoCADVersion",
            autocad_version,
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if completed.returncode != 0:
        detail = (completed.stdout or "")[-800:] + (completed.stderr or "")[-400:]
        raise RuntimeError(f"插件包构建失败：{detail}")

    releases = root / "artifacts" / "releases"
    zips = sorted(releases.glob(f"AgentBridge-*-AutoCAD-{autocad_version}.zip"))
    if not zips:
        raise RuntimeError("未找到构建产物 zip")
    archive = zips[-1]

    appdata = os.getenv("APPDATA") or str(Path.home())
    plugins_root = Path(appdata) / "Autodesk" / "ApplicationPlugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    target = plugins_root / "AgentBridge.bundle"
    if target.exists():
        shutil.rmtree(target)

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        bundle = next(Path(tmp).rglob("AgentBridge.bundle"), None)
        if bundle is None:
            raise RuntimeError("zip 内缺少 AgentBridge.bundle")
        shutil.copytree(bundle, target)

    return {
        "ok": True,
        "installed": str(target),
        "artifact": archive.name,
        "message": "插件包已安装到 %APPDATA%\\Autodesk\\ApplicationPlugins\\AgentBridge.bundle，启动 AutoCAD 即自动加载。",
    }


__all__ = ["build_and_install_autocad_plugin"]
