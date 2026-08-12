"""JSON-backed persistence for task delivery records."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

from delivery.models import DeliveryRecord


def default_delivery_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "deliveries.json"


class DeliveryStore:
    """Thread-safe JSON store keyed by task_id."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path or default_delivery_path())
        self._lock = threading.RLock()
        self._records: Dict[str, DeliveryRecord] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._records = {
                    task_id: DeliveryRecord.model_validate(item)
                    for task_id, item in data.items()
                }
            except (OSError, ValueError, TypeError) as exc:
                backup = self._path.with_suffix(".json.bak")
                try:
                    self._path.replace(backup)
                except OSError:
                    pass
                raise RuntimeError(f"delivery store unreadable: {exc}") from exc

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {task_id: record.model_dump() for task_id, record in self._records.items()}
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._path)

    def list(self) -> List[DeliveryRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda item: item.updated_at, reverse=True)

    def get(self, task_id: str) -> Optional[DeliveryRecord]:
        with self._lock:
            return self._records.get(task_id)

    def upsert(self, record: DeliveryRecord) -> DeliveryRecord:
        with self._lock:
            self._records[record.task_id] = record
            self._save_locked()
            return record
