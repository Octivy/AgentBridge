"""Bridge supervisor: auto-restart dead bridges and record visible events.

Product stance: a bridge the user marked ``auto_start`` should keep running.
This background thread polls those bridges, detects a dead process, restarts
it (within a restart budget so a broken config or a stuck port cannot turn
into a restart storm), and attributes the crash — most importantly a port
conflict — so the panel can show an actionable reason instead of a bare
"离线" badge.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from host_config.events import (
    BRIDGE_AUTO_RESTARTED,
    BRIDGE_CRASHED,
    PORT_CONFLICT,
    RESTART_BUDGET_EXHAUSTED,
    ConnectionEventLog,
    connection_event_log,
)
from host_config.service import HostConfigService, host_config_service

# Log patterns that indicate the bridge died because its port was taken.
PORT_CONFLICT_MARKERS = (
    "address already in use",
    "only one usage of each socket address",
    "10048",
    "端口被占用",
    "winsock error",
)

_LOG_TAIL_BYTES = 4096


def _default_log_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "host-logs"


class BridgeSupervisor:
    """Poll auto_start bridges and keep their processes alive."""

    def __init__(
        self,
        service: Optional[HostConfigService] = None,
        events: Optional[ConnectionEventLog] = None,
        interval_seconds: float = 5.0,
        max_restarts: int = 5,
        restart_window_seconds: float = 300.0,
        log_dir: Optional[Path] = None,
    ) -> None:
        self._service = service or host_config_service
        self._events = events or connection_event_log
        self._interval = max(1.0, interval_seconds)
        self._max_restarts = max(1, max_restarts)
        self._window = max(30.0, restart_window_seconds)
        self._log_dir = log_dir or _default_log_dir()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._restarts: Dict[str, List[float]] = {}
        self._lock = threading.RLock()

    # ----- lifecycle -----

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="bridge-supervisor", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    def status(self) -> Dict[str, Any]:
        with self._lock:
            restarts = {
                host_id: len([t for t in stamps if time.monotonic() - t < self._window])
                for host_id, stamps in self._restarts.items()
            }
        return {
            "running": self.running(),
            "interval_seconds": self._interval,
            "max_restarts_per_window": self._max_restarts,
            "restart_window_seconds": self._window,
            "restarts_in_window": restarts,
        }

    # ----- polling -----

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - the loop must survive any single host's failure
                continue

    def poll_once(self) -> None:
        """One supervision pass; public so tests can drive it deterministically."""

        for config in self._service.list_configs():
            if not (config.enabled and config.auto_start and config.launch.command.strip()):
                continue
            try:
                status = self._service.status(config.host_id)
            except Exception:  # noqa: BLE001
                continue
            if status.process_running:
                continue
            if not self._restart_allowed(config.host_id):
                continue

            reason = self._crash_reason(config.host_id)
            try:
                self._service.start(config.host_id)
                self._record_restart(config.host_id)
                message = "桥进程已退出，已自动重启"
                if reason:
                    message += f"（检测到：{reason}）"
                self._events.record(config.host_id, BRIDGE_AUTO_RESTARTED, message)
                if reason == "端口被占用":
                    self._events.record(
                        config.host_id,
                        PORT_CONFLICT,
                        "桥进程因端口被占用退出，请释放端口或修改连接配置。",
                        level="warning",
                    )
            except Exception as exc:  # noqa: BLE001
                self._events.record(config.host_id, BRIDGE_CRASHED, f"自动重启失败：{exc}", level="error")
                self._record_restart(config.host_id)

    # ----- restart budget -----

    def _restart_allowed(self, host_id: str) -> bool:
        with self._lock:
            stamps = [t for t in self._restarts.get(host_id, []) if time.monotonic() - t < self._window]
            self._restarts[host_id] = stamps
            return len(stamps) < self._max_restarts

    def _record_restart(self, host_id: str) -> None:
        with self._lock:
            stamps = [t for t in self._restarts.get(host_id, []) if time.monotonic() - t < self._window]
            stamps.append(time.monotonic())
            self._restarts[host_id] = stamps
            if len(stamps) >= self._max_restarts:
                self._events.record(
                    host_id,
                    RESTART_BUDGET_EXHAUSTED,
                    f"在 {int(self._window)} 秒内已自动重启 {len(stamps)} 次，暂停自愈，请检查端口或桥接日志。",
                    level="warning",
                )

    # ----- crash attribution -----

    def _crash_reason(self, host_id: str) -> str:
        tail = self._read_log_tail(host_id)
        if not tail:
            return "进程异常退出"
        if any(marker in tail for marker in PORT_CONFLICT_MARKERS):
            return "端口被占用"
        return "进程异常退出"

    def _read_log_tail(self, host_id: str, size: int = _LOG_TAIL_BYTES) -> str:
        path = self._log_dir / f"{host_id}.log"
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                length = handle.tell()
                handle.seek(max(0, length - size))
                return handle.read(size).decode("utf-8", errors="replace").lower()
        except OSError:
            return ""


bridge_supervisor = BridgeSupervisor()


__all__ = ["BridgeSupervisor", "bridge_supervisor", "PORT_CONFLICT_MARKERS"]
