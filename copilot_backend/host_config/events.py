"""Persistent connection lifecycle events (self-healing visibility).

The config center's connection actions (start/stop a bridge, auto-restart a
crashed process, clean stale registrations, detect a port conflict) append to
a small JSON ring buffer so the panel can show *what happened and why* instead
of a bare "离线" badge.

Events are keyed by ``host_id`` (``""`` for system-wide events) and carry a
``kind``, ``level`` and human-readable ``message``.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MAX_EVENTS = 200

# Event kinds used across the codebase.
BRIDGE_STARTED = "bridge_started"
BRIDGE_STOPPED = "bridge_stopped"
BRIDGE_CRASHED = "bridge_crashed"
BRIDGE_AUTO_RESTARTED = "bridge_auto_restarted"
PORT_CONFLICT = "port_conflict"
RESTART_BUDGET_EXHAUSTED = "restart_budget_exhausted"
STALE_REGISTRATION_CLEANED = "stale_registration_cleaned"


def default_events_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "connection_events.json"


class ConnectionEventLog:
    """Thread-safe JSON ring buffer of connection lifecycle events."""

    def __init__(self, path: Optional[Path] = None, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self._path = Path(path) if path is not None else default_events_path()
        self._max = max(1, max_events)
        self._lock = threading.RLock()
        self._events: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._events = [item for item in data if isinstance(item, dict)][-self._max :]
            except (OSError, ValueError):
                self._events = []

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._events, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def record(self, host_id: str, kind: str, message: str, level: str = "info") -> Dict[str, Any]:
        with self._lock:
            event: Dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "host_id": host_id or "",
                "kind": kind,
                "level": level,
                "message": message,
            }
            self._events.append(event)
            self._events = self._events[-self._max :]
            self._save_locked()
            return dict(event)

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self._events[-max(limit, 0) :]))

    def clear(self) -> Dict[str, Any]:
        with self._lock:
            count = len(self._events)
            self._events = []
            self._save_locked()
        return {"cleared": True, "removed": count}


connection_event_log = ConnectionEventLog()


__all__ = [
    "BRIDGE_AUTO_RESTARTED",
    "BRIDGE_CRASHED",
    "BRIDGE_STARTED",
    "BRIDGE_STOPPED",
    "PORT_CONFLICT",
    "RESTART_BUDGET_EXHAUSTED",
    "STALE_REGISTRATION_CLEANED",
    "ConnectionEventLog",
    "connection_event_log",
    "default_events_path",
]
