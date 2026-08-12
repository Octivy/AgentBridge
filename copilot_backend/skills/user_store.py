from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from cadmcp.tool_registry import PRODUCT_MVP_TOOL_NAMES
from shared import settings
from shared.schemas import (
    PlannerTaskDetailResponse,
    SkillDraftApprovalRequest,
    SkillDraftCreateRequest,
    SkillDraftResponse,
    SkillDraftUpdateRequest,
)


class SkillDraftStore:
    """Persistent, review-only storage for user-created Skill drafts."""

    def __init__(self, path: str | Path):
        self._path = Path(path).expanduser() if str(path).strip() else None
        self._lock = threading.RLock()

    def list(self) -> list[SkillDraftResponse]:
        with self._lock:
            return sorted(self._load(), key=lambda item: item.updated_at, reverse=True)

    def get(self, skill_id: str) -> Optional[SkillDraftResponse]:
        normalized = (skill_id or "").strip()
        with self._lock:
            return next((item for item in self._load() if item.skill_id == normalized), None)

    def create(self, request: SkillDraftCreateRequest) -> SkillDraftResponse:
        tools = self._validate_tools(request.mcp_tools)
        steps = self._clean_values(request.plan_steps)
        now = datetime.now(timezone.utc)
        draft = SkillDraftResponse(
            skill_id=self._new_skill_id(request.name),
            name=request.name.strip(),
            description=request.description.strip(),
            category=(request.category or "user").strip() or "user",
            user_goal=request.user_goal.strip(),
            plan_steps=steps,
            mcp_tools=tools,
            source_task_id=self._optional_text(request.source_task_id),
            source_trace_id=self._optional_text(request.source_trace_id),
            source_skill_ids=self._clean_values(request.source_skill_ids),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            items = self._load()
            items.append(draft)
            self._save(items)
        return draft

    def create_from_task(self, task: PlannerTaskDetailResponse, *, name: str = "") -> SkillDraftResponse:
        if task.task_status != "completed":
            raise ValueError("only completed planner tasks can be converted to a Skill draft")
        planner_state = task.planner_state
        completed_steps = list(planner_state.completed_steps) if planner_state else []
        executed_tools = list(planner_state.executed_tools) if planner_state else []
        selected_skills = list(planner_state.selected_skills) if planner_state else []
        draft_name = name.strip() or self._suggest_name(task.user_goal)
        description = task.final_response.strip()
        if len(description) > 1000:
            description = description[:997] + "..."
        return self.create(
            SkillDraftCreateRequest(
                name=draft_name,
                description=description,
                category="task-derived",
                user_goal=task.user_goal,
                plan_steps=completed_steps or [task.user_goal],
                mcp_tools=executed_tools,
                source_task_id=task.task_id,
                source_trace_id=task.trace_id,
                source_skill_ids=selected_skills,
            )
        )

    def update(self, skill_id: str, request: SkillDraftUpdateRequest) -> SkillDraftResponse:
        tools = self._validate_tools(request.mcp_tools)
        with self._lock:
            items = self._load()
            index = self._find_index(items, skill_id)
            current = items[index]
            updated = current.model_copy(
                update={
                    "version": current.version + 1,
                    "status": "draft",
                    "name": request.name.strip(),
                    "description": request.description.strip(),
                    "category": (request.category or "user").strip() or "user",
                    "user_goal": request.user_goal.strip(),
                    "plan_steps": self._clean_values(request.plan_steps),
                    "mcp_tools": tools,
                    "source_task_id": self._optional_text(request.source_task_id),
                    "source_trace_id": self._optional_text(request.source_trace_id),
                    "source_skill_ids": self._clean_values(request.source_skill_ids),
                    "updated_at": datetime.now(timezone.utc),
                    "review_required": True,
                    "validation_errors": [],
                    "reviewer": None,
                    "review_note": "",
                    "reviewed_at": None,
                    "enabled": False,
                }
            )
            items[index] = updated
            self._save(items)
            return updated

    def validate(self, skill_id: str) -> SkillDraftResponse:
        with self._lock:
            items = self._load()
            index = self._find_index(items, skill_id)
            current = items[index]
            errors = self._validation_errors(current)
            validated = current.model_copy(
                update={
                    "status": "validated" if not errors else "draft",
                    "validation_errors": errors,
                    "updated_at": datetime.now(timezone.utc),
                    "review_required": True,
                    "enabled": False,
                }
            )
            items[index] = validated
            self._save(items)
            return validated

    def approve(self, skill_id: str, request: SkillDraftApprovalRequest) -> SkillDraftResponse:
        with self._lock:
            items = self._load()
            index = self._find_index(items, skill_id)
            current = items[index]
            if current.status != "validated" or current.validation_errors:
                raise ValueError("Skill draft must pass validation before approval")
            now = datetime.now(timezone.utc)
            approved = current.model_copy(
                update={
                    "status": "approved",
                    "review_required": False,
                    "reviewer": request.reviewer.strip(),
                    "review_note": request.review_note.strip(),
                    "reviewed_at": now,
                    "updated_at": now,
                    "enabled": False,
                }
            )
            items[index] = approved
            self._save(items)
            return approved

    @staticmethod
    def _validate_tools(tool_names: Iterable[str]) -> list[str]:
        tools = SkillDraftStore._clean_values(tool_names)
        unsupported = sorted(set(tools) - PRODUCT_MVP_TOOL_NAMES)
        if unsupported:
            raise ValueError("Skill draft references tools outside the product whitelist: " + ", ".join(unsupported))
        return tools

    @staticmethod
    def _validation_errors(draft: SkillDraftResponse) -> list[str]:
        errors: list[str] = []
        if not draft.name.strip():
            errors.append("name is required")
        if not draft.user_goal.strip():
            errors.append("user_goal is required")
        if not draft.plan_steps:
            errors.append("at least one reproducible plan step is required")
        if not draft.mcp_tools:
            errors.append("at least one product MCP tool is required")
        unsupported = sorted(set(draft.mcp_tools) - PRODUCT_MVP_TOOL_NAMES)
        if unsupported:
            errors.append("unsupported tools: " + ", ".join(unsupported))
        return errors

    @staticmethod
    def _find_index(items: list[SkillDraftResponse], skill_id: str) -> int:
        normalized = (skill_id or "").strip()
        for index, item in enumerate(items):
            if item.skill_id == normalized:
                return index
        raise KeyError("Skill draft not found")

    @staticmethod
    def _clean_values(values: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return cleaned

    @staticmethod
    def _optional_text(value: Optional[str]) -> Optional[str]:
        normalized = (value or "").strip()
        return normalized or None

    @staticmethod
    def _suggest_name(user_goal: str) -> str:
        goal = (user_goal or "").strip()
        return goal[:60] if goal else "复用任务流程"

    @staticmethod
    def _new_skill_id(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
        return f"{slug or 'user-skill'}-{uuid.uuid4().hex[:8]}"

    def _load(self) -> list[SkillDraftResponse]:
        if self._path is None or not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read Skill draft store: {exc}") from exc
        raw_items = payload.get("skills", []) if isinstance(payload, dict) else payload
        return [SkillDraftResponse.model_validate(item) for item in raw_items]

    def _save(self, items: list[SkillDraftResponse]) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {
            "schema_version": "1.0",
            "skills": [item.model_dump(mode="json") for item in items],
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)


skill_draft_store = SkillDraftStore(settings.CADCOPILOT_SKILL_DRAFT_STORE_PATH)
