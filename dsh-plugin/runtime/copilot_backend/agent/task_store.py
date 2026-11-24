r"""Persistent records for panel agent tasks (status, steps, pending write).

The panel runs agent tasks asynchronously so the user can watch progress and
confirm write operations. Each task's state lives here, persisted to
``%LOCALAPPDATA%\AgentBridge\agent_tasks.json`` (mirrors the delivery store),
and survives backend restarts: a task that stopped at ``needs_confirmation``
can be confirmed long after it was started.

``history`` (the canonical model message list) is stored for resume but is
stripped from API views.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTaskRecord(BaseModel):
    """Everything needed to display, resume, and audit one agent task."""

    task_id: str
    user_goal: str = ""
    approval: str = "full"
    tool_scope: str = "hosts"
    provider: str = ""
    protocol: str = ""
    # running | needs_confirmation | completed | failed | no_tools
    status: str = "running"
    stopped_reason: str = ""
    final_text: str = ""
    error: str = ""
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    executed_tools: List[Dict[str, Any]] = Field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 12
    pending_write: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    def remaining_iterations(self) -> int:
        return max(self.max_iterations - self.iterations, 0)

    def view(self) -> Dict[str, Any]:
        """API-safe payload: history is internal and can be large."""

        payload = self.model_dump()
        payload.pop("history", None)
        return payload


def default_task_store_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "agent_tasks.json"


class AgentTaskStore:
    """Thread-safe JSON store keyed by task_id, capped to the newest records."""

    MAX_RECORDS = 50

    def __init__(self, path: Optional[Path] = None, max_records: int = MAX_RECORDS) -> None:
        self._path = Path(path or default_task_store_path())
        self._lock = threading.RLock()
        self._records: Dict[str, AgentTaskRecord] = {}
        self._max_records = max(1, max_records)
        self._last_stamp = ""
        self._load()

    def _stamp(self) -> str:
        stamp = _now()
        if self._last_stamp and stamp <= self._last_stamp:
            base = datetime.fromisoformat(self._last_stamp)
            stamp = (base + timedelta(microseconds=1)).isoformat()
        self._last_stamp = stamp
        return stamp

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._records = {
                    task_id: AgentTaskRecord.model_validate(item)
                    for task_id, item in data.items()
                }
            except (OSError, ValueError, TypeError) as exc:
                backup = self._path.with_suffix(".json.bak")
                try:
                    self._path.replace(backup)
                except OSError:
                    pass
                raise RuntimeError(f"agent task store unreadable: {exc}") from exc

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {task_id: record.model_dump() for task_id, record in self._records.items()}
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def _trim_locked(self) -> None:
        if len(self._records) <= self._max_records:
            return
        ordered = sorted(self._records.values(), key=lambda item: item.updated_at)
        for record in ordered[: len(self._records) - self._max_records]:
            self._records.pop(record.task_id, None)

    def touch(self, record: AgentTaskRecord) -> None:
        record.updated_at = self._stamp()

    def get(self, task_id: str) -> Optional[AgentTaskRecord]:
        with self._lock:
            return self._records.get(task_id)

    def list(self, limit: int = 20) -> List[AgentTaskRecord]:
        with self._lock:
            ordered = sorted(self._records.values(), key=lambda item: item.updated_at, reverse=True)
            return ordered[: max(limit, 0)]

    def upsert(self, record: AgentTaskRecord) -> AgentTaskRecord:
        with self._lock:
            self._records[record.task_id] = record
            self._trim_locked()
            self._save_locked()
            return record


agent_task_store = AgentTaskStore()


__all__ = [
    "AgentTaskRecord",
    "AgentTaskStore",
    "agent_task_store",
    "default_task_store_path",
]
