"""Models for task delivery (deliverables and handoff summary)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Deliverable(BaseModel):
    name: str
    kind: str = "file"  # file | screenshot | report | model | other
    path: str
    description: str = ""
    created_at: str = ""


class HandoffSummary(BaseModel):
    summary: str = ""
    verification_steps: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    updated_at: str = ""


class DeliveryRecord(BaseModel):
    task_id: str
    user_goal: str = ""
    status: str = "unknown"
    deliverables: List[Deliverable] = Field(default_factory=list)
    handoff: HandoffSummary = Field(default_factory=HandoffSummary)
    created_at: str = ""
    updated_at: str = ""


class DeliveryTaskView(BaseModel):
    task_id: str
    user_goal: str
    status: str
    deliverable_count: int
    deliverables: List[Deliverable]
    handoff: HandoffSummary
    created_at: str
    updated_at: str


class DeliverableCreate(BaseModel):
    name: str
    kind: str = "file"
    path: str
    description: str = ""


class HandoffUpdate(BaseModel):
    summary: str = ""
    verification_steps: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
