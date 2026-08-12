"""Configuration center service: lifecycle, health probing and status."""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from host_config.models import (
    HostAdapterConfig,
    HostConfigCreate,
    HostConfigStatus,
    HostConfigUpdate,
    HostTestResult,
)
from host_config.store import HostConfigStore
from host_runtime.client import HostClient
from host_runtime.registry import default_registry_dir, discover_hosts


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HostConfigService:
    """Manage configured software bridges and their runtime processes."""

    def __init__(
        self,
        store: Optional[HostConfigStore] = None,
        registry_dir: Optional[Path] = None,
    ) -> None:
        self._store = store or HostConfigStore(repo_root=_repo_root())
        self._registry_dir = Path(registry_dir or default_registry_dir())
        self._processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    # ----- configuration CRUD -----

    def list_configs(self) -> List[HostAdapterConfig]:
        return self._store.list()

    def get_config(self, host_id: str) -> Optional[HostAdapterConfig]:
        return self._store.get(host_id)

    def create_config(self, request: HostConfigCreate) -> HostAdapterConfig:
        if self._store.get(request.host_id) is not None:
            raise ValueError(f"host config already exists: {request.host_id}")
        stamp = _now()
        config = HostAdapterConfig(
            host_id=request.host_id.strip(),
            name=request.name.strip(),
            host_kind=request.host_kind.strip().lower(),
            product=request.product.strip(),
            enabled=request.enabled,
            auto_start=request.auto_start,
            launch=request.launch,
            notes=request.notes,
            created_at=stamp,
            updated_at=stamp,
        )
        if not config.host_id or not config.name or not config.host_kind:
            raise ValueError("host_id, name and host_kind are required")
        return self._store.upsert(config)

    def update_config(self, host_id: str, request: HostConfigUpdate) -> HostAdapterConfig:
        existing = self._store.get(host_id)
        if existing is None:
            raise KeyError(f"host config not found: {host_id}")
        update = request.model_dump(exclude_unset=True)
        updated = existing.model_copy(update=update)
        updated.updated_at = _now()
        return self._store.upsert(updated)

    def delete_config(self, host_id: str) -> bool:
        self.stop(host_id)
        return self._store.delete(host_id)

    # ----- lifecycle -----

    def start(self, host_id: str) -> HostConfigStatus:
        config = self._store.get(host_id)
        if config is None:
            raise KeyError(f"host config not found: {host_id}")
        if not config.enabled:
            raise ValueError(f"host is disabled: {host_id}")
        launch = config.launch
        if not launch.command.strip():
            raise ValueError(f"no launch command configured for {host_id}")

        with self._lock:
            existing = self._processes.get(host_id)
            if existing is not None and existing.poll() is None:
                return self.status(host_id)
            env = os.environ.copy()
            env.update(launch.env)
            cwd = launch.cwd or str(_repo_root())
            log_dir = Path(os.getenv("LOCALAPPDATA") or str(Path.home())) / "AgentBridge" / "host-logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{host_id}.log"
            stdout = open(log_path, "a", encoding="utf-8", errors="replace")
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(
                [launch.command, *launch.args],
                cwd=cwd,
                env=env,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self._processes[host_id] = process
        return self.status(host_id)

    def stop(self, host_id: str) -> HostConfigStatus:
        with self._lock:
            process = self._processes.pop(host_id, None)
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    process.terminate()
        return self.status(host_id)

    def auto_start(self) -> List[HostConfigStatus]:
        started: List[HostConfigStatus] = []
        for config in self._store.list():
            if config.enabled and config.auto_start and config.launch.command.strip():
                try:
                    started.append(self.start(config.host_id))
                except (ValueError, OSError):
                    continue
        return started

    # ----- status & health -----

    def list_status(self) -> List[HostConfigStatus]:
        return [self.status(config.host_id) for config in self._store.list()]

    def status(self, host_id: str) -> HostConfigStatus:
        config = self._store.get(host_id)
        if config is None:
            raise KeyError(f"host config not found: {host_id}")
        return self._status(config)

    def _status(self, config: HostAdapterConfig) -> HostConfigStatus:
        process = self._processes.get(config.host_id)
        process_running = process is not None and process.poll() is None
        pid = process.pid if process_running else None

        registration = next(
            (item for item in discover_hosts(self._registry_dir) if item.host_kind == config.host_kind),
            None,
        )
        registered = registration is not None
        health_ok = False
        product_version = ""
        endpoint = ""
        error = ""
        if registered:
            endpoint = registration.endpoint
            product_version = registration.product_version
            try:
                health = HostClient(registration.endpoint, registration.token, timeout_seconds=3).health()
                health_ok = bool(health and health.get("ok"))
                if not health_ok:
                    error = "registered host reported unhealthy"
            except Exception as exc:  # noqa: BLE001
                error = f"health probe failed: {exc}"
        elif config.launch.command.strip() and not process_running:
            error = "未发现已注册的宿主，请先在软件内启动适配器"

        return HostConfigStatus(
            host_id=config.host_id,
            name=config.name,
            host_kind=config.host_kind,
            product=config.product,
            enabled=config.enabled,
            auto_start=config.auto_start,
            configured=bool(config.launch.command.strip()),
            process_running=process_running,
            pid=pid,
            registered=registered,
            registered_host_id=registration.host_id if registered else "",
            product_version=product_version,
            endpoint=endpoint,
            health_ok=health_ok,
            error=error,
        )

    def test(self, host_id: str) -> HostTestResult:
        config = self._store.get(host_id)
        if config is None:
            raise KeyError(f"host config not found: {host_id}")
        registration = next(
            (item for item in discover_hosts(self._registry_dir) if item.host_kind == config.host_kind),
            None,
        )
        if registration is None:
            return HostTestResult(
                host_id=host_id,
                ok=False,
                message="未发现已注册的宿主，请先在软件内启动适配器（add-on / 插件 / 脚本）",
            )
        try:
            health = HostClient(registration.endpoint, registration.token, timeout_seconds=5).health()
        except Exception as exc:  # noqa: BLE001
            return HostTestResult(host_id=host_id, ok=False, message=f"健康检查失败: {exc}")
        ok = bool(health and health.get("ok"))
        return HostTestResult(
            host_id=host_id,
            ok=ok,
            product=str(health.get("product") or ""),
            product_version=str(health.get("product_version") or ""),
            endpoint=registration.endpoint,
            message="连接正常" if ok else "宿主已注册但健康检查未通过",
        )


host_config_service = HostConfigService()


__all__ = ["HostConfigService", "host_config_service"]
