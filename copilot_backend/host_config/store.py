"""JSON-backed persistence for host adapter configurations."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

from host_config.models import HostAdapterConfig, LaunchSpec


def default_config_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "host_configs.json"


def default_seed_configs(repo_root: Path) -> Dict[str, HostAdapterConfig]:
    """Seed entries for the four target software families."""

    powershell = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    scripts = repo_root / "scripts"

    def now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    stamp = now()
    return {
        "autocad": HostAdapterConfig(
            host_id="autocad",
            name="AutoCAD",
            host_kind="autocad",
            product="AutoCAD",
            enabled=True,
            auto_start=False,
            launch=LaunchSpec(
                command=powershell,
                args=["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / "start-cadmcp.ps1")],
                env_vars=["CADMCP_BRIDGE_URL", "CADMCP_BRIDGE_TOKEN", "CADCOPILOT_LOCAL_BRIDGE_URL", "CADCOPILOT_LOCAL_BRIDGE_TOKEN"],
                cwd=str(repo_root),
            ),
            notes="通过 cadmcp 连接 AutoCAD 插件（LocalToolBridge）。需先在 AutoCAD 中加载插件。",
            created_at=stamp,
            updated_at=stamp,
        ),
        "blender": HostAdapterConfig(
            host_id="blender",
            name="Blender",
            host_kind="blender",
            product="Blender",
            enabled=True,
            auto_start=False,
            launch=LaunchSpec(
                command=powershell,
                args=["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / "start-hostmcp.ps1")],
                env_vars=["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT", "HOSTMCP_HOST", "HOSTMCP_PORT"],
                cwd=str(repo_root),
            ),
            notes="hostmcp 聚合所有注册宿主；Blender add-on 需在 Blender 内启用并注册。",
            created_at=stamp,
            updated_at=stamp,
        ),
        "sketchup": HostAdapterConfig(
            host_id="sketchup",
            name="SketchUp",
            host_kind="sketchup",
            product="SketchUp",
            enabled=True,
            auto_start=False,
            launch=LaunchSpec(
                command=powershell,
                args=["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / "start-hostmcp.ps1")],
                env_vars=["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT", "HOSTMCP_HOST", "HOSTMCP_PORT"],
                cwd=str(repo_root),
            ),
            notes="hostmcp 聚合所有注册宿主；SketchUp 扩展需在 SketchUp 内加载并注册。",
            created_at=stamp,
            updated_at=stamp,
        ),
        "rhino": HostAdapterConfig(
            host_id="rhino",
            name="Rhino",
            host_kind="rhino",
            product="Rhino",
            enabled=True,
            auto_start=False,
            launch=LaunchSpec(
                command=powershell,
                args=["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / "start-hostmcp.ps1")],
                env_vars=["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT", "HOSTMCP_HOST", "HOSTMCP_PORT"],
                cwd=str(repo_root),
            ),
            notes="hostmcp 聚合所有注册宿主；Rhino 适配器需在 Rhino 内加载并注册。",
            created_at=stamp,
            updated_at=stamp,
        ),
    }


class HostConfigStore:
    """Thread-safe JSON store for host adapter configurations."""

    def __init__(self, path: Optional[Path] = None, repo_root: Optional[Path] = None) -> None:
        self._path = Path(path or default_config_path())
        self._lock = threading.RLock()
        self._configs: Dict[str, HostAdapterConfig] = {}
        self._repo_root = repo_root
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                    self._configs = {
                        host_id: HostAdapterConfig.model_validate(item)
                        for host_id, item in data.items()
                    }
                    return
                except (OSError, ValueError, TypeError) as exc:
                    # Corrupt file: keep a backup and reseed rather than crash.
                    backup = self._path.with_suffix(".json.bak")
                    try:
                        self._path.replace(backup)
                    except OSError:
                        pass
                    raise RuntimeError(f"host config store unreadable: {exc}") from exc
            if self._repo_root is not None:
                self._configs = default_seed_configs(self._repo_root)
                self._save_locked()

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {host_id: config.model_dump() for host_id, config in self._configs.items()}
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def list(self) -> List[HostAdapterConfig]:
        with self._lock:
            return sorted(self._configs.values(), key=lambda item: item.host_id)

    def get(self, host_id: str) -> Optional[HostAdapterConfig]:
        with self._lock:
            return self._configs.get(host_id)

    def upsert(self, config: HostAdapterConfig) -> HostAdapterConfig:
        with self._lock:
            self._configs[config.host_id] = config
            self._save_locked()
            return config

    def delete(self, host_id: str) -> bool:
        with self._lock:
            existed = self._configs.pop(host_id, None) is not None
            if existed:
                self._save_locked()
            return existed
