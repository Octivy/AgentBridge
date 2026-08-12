"""Delivery service: register deliverables and handoff summaries for tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from delivery.models import (
    Deliverable,
    DeliverableCreate,
    DeliveryRecord,
    DeliveryTaskView,
    HandoffSummary,
    HandoffUpdate,
)
from delivery.store import DeliveryStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeliveryService:
    """Track what a task produced and how to hand it off."""

    def __init__(self, store: Optional[DeliveryStore] = None) -> None:
        self._store = store or DeliveryStore()

    def _ensure_record(self, task_id: str, user_goal: str = "") -> DeliveryRecord:
        existing = self._store.get(task_id)
        if existing is not None:
            return existing
        stamp = _now()
        return DeliveryRecord(
            task_id=task_id,
            user_goal=user_goal,
            created_at=stamp,
            updated_at=stamp,
        )

    def add_deliverable(self, task_id: str, request: DeliverableCreate) -> DeliveryTaskView:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("task_id is required")
        name = request.name.strip()
        if not name:
            raise ValueError("deliverable name is required")
        if not request.path.strip():
            raise ValueError("deliverable path is required")

        record = self._ensure_record(task_id)
        existing_names = {item.name for item in record.deliverables}
        if name in existing_names:
            record.deliverables = [item for item in record.deliverables if item.name != name]
        record.deliverables.append(
            Deliverable(
                name=name,
                kind=request.kind or "file",
                path=request.path.strip(),
                description=request.description,
                created_at=_now(),
            )
        )
        record.updated_at = _now()
        self._store.upsert(record)
        return self._view(record)

    def set_handoff(self, task_id: str, request: HandoffUpdate) -> DeliveryTaskView:
        task_id = task_id.strip()
        record = self._ensure_record(task_id)
        record.handoff = HandoffSummary(
            summary=request.summary,
            verification_steps=list(request.verification_steps),
            next_steps=list(request.next_steps),
            updated_at=_now(),
        )
        record.updated_at = _now()
        self._store.upsert(record)
        return self._view(record)

    def get(self, task_id: str) -> Optional[DeliveryTaskView]:
        record = self._store.get(task_id)
        return self._view(record) if record is not None else None

    def list(self, limit: int = 20) -> List[DeliveryTaskView]:
        return [self._view(record) for record in self._store.list()[: max(limit, 0)]]

    def _view(self, record: DeliveryRecord) -> DeliveryTaskView:
        return DeliveryTaskView(
            task_id=record.task_id,
            user_goal=record.user_goal,
            status=record.status,
            deliverable_count=len(record.deliverables),
            deliverables=list(record.deliverables),
            handoff=record.handoff,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


delivery_service = DeliveryService()


__all__ = ["DeliveryService", "delivery_service"]
