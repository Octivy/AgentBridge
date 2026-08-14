"""One-click SketchUp extension install.

SketchUp loads .rbz extensions found in the user Extensions folder
(%APPDATA%\\SketchUp\\SketchUp <ver>\\SketchUp\\Extensions) at startup, so the
client can install the AgentBridge host by copying the bundle there. A SketchUp
restart is required for it to take effect.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Dict, List


EXTENSION_NAME = "AgentBridge-Host-1.0.0.rbz"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sketchup_appdata_root() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "SketchUp"


def detect_sketchup_versions(root: Path | None = None) -> List[str]:
    """Return detected SketchUp version folders, newest first (e.g. '2025')."""

    base = root or sketchup_appdata_root()
    if not base.is_dir():
        return []
    versions: List[str] = []
    for entry in base.glob("SketchUp *"):
        if entry.is_dir():
            version = entry.name.replace("SketchUp ", "").strip()
            if version:
                versions.append(version)
    return sorted(versions, reverse=True)


def extensions_dir(version: str, root: Path | None = None) -> Path:
    base = root or sketchup_appdata_root()
    return base / f"SketchUp {version}" / "SketchUp" / "Extensions"


def build_sketchup_rbz(repo_root: Path | None = None) -> bytes:
    """Build the .rbz bundle (loader + host) in memory."""

    root = repo_root or _repo_root()
    source = root / "adapters" / "sketchup"
    payload = {
        "cadcopilot_extension.rb": (source / "cadcopilot_extension.rb").read_bytes(),
        "cadcopilot_host.rb": (source / "cadcopilot_host.rb").read_bytes(),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def install_sketchup_extension(
    root: Path | None = None,
    repo_root: Path | None = None,
) -> Dict[str, object]:
    versions = detect_sketchup_versions(root)
    if not versions:
        return {
            "ok": False,
            "installed": [],
            "sketchup_versions": [],
            "message": "未检测到 SketchUp（%APPDATA%\\SketchUp\\SketchUp *）",
        }
    rbz = build_sketchup_rbz(repo_root)
    installed: List[str] = []
    for version in versions:
        directory = extensions_dir(version, root)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / EXTENSION_NAME
        temp = target.with_suffix(".tmp")
        temp.write_bytes(rbz)
        os.replace(temp, target)
        installed.append(str(target))
    removed = _remove_stale_loose_copies(root)
    message = "已安装到 SketchUp，请重启 SketchUp 生效"
    if removed:
        message += f"；同时清理了 {len(removed)} 个旧版裸拷贝（旧文件会导致宿主崩溃）"
    return {
        "ok": True,
        "installed": installed,
        "removed_stale": removed,
        "sketchup_versions": versions,
        "message": message,
    }


def _remove_stale_loose_copies(root: Path | None = None) -> List[str]:
    """Remove old loose .rb copies in SketchUp's Plugins dir.

    Older installs copied the host straight into Plugins/; SketchUp loads that
    copy *and* the .rbz bundle, so the stale copy crashes first and breaks
    registration. The .rbz in Extensions/ is the single source of truth.
    """

    base = root or sketchup_appdata_root()
    removed: List[str] = []
    for version in detect_sketchup_versions(base):
        plugins_dir = base / f"SketchUp {version}" / "SketchUp" / "Plugins"
        for name in ("cadcopilot_host.rb", "cadcopilot_extension.rb"):
            path = plugins_dir / name
            try:
                if path.is_file():
                    path.unlink()
                    removed.append(str(path))
            except OSError:
                continue
    return removed


def sketchup_extension_status(root: Path | None = None) -> Dict[str, object]:
    versions = detect_sketchup_versions(root)
    results: List[Dict[str, object]] = []
    for version in versions:
        target = extensions_dir(version, root) / EXTENSION_NAME
        results.append(
            {
                "version": version,
                "installed": target.exists(),
                "path": str(target),
            }
        )
    return {
        "ok": True,
        "sketchup_versions": versions,
        "extensions": results,
    }


__all__ = [
    "EXTENSION_NAME",
    "build_sketchup_rbz",
    "detect_sketchup_versions",
    "extensions_dir",
    "install_sketchup_extension",
    "sketchup_extension_status",
]
