import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.schemas import (
    PlannerState,
    PlannerTaskDetailResponse,
    SkillDraftCreateRequest,
    SkillDraftApprovalRequest,
    SkillDraftUpdateRequest,
)
from skills.user_store import SkillDraftStore


class SkillDraftStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "skill-drafts.json"
        self.store = SkillDraftStore(self.path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_completed_task_becomes_review_only_persistent_draft(self):
        now = datetime.now(timezone.utc)
        task = PlannerTaskDetailResponse(
            task_id="task-1",
            trace_id="trace-1",
            user_goal="读取图层并绘制外围轮廓",
            task_status="completed",
            created_at=now,
            updated_at=now,
            final_response="外围轮廓任务已完成。",
            planner_state=PlannerState(
                task_status="completed",
                executed_tools=["get_drawing_snapshot", "arch_extract_outer_outline"],
                selected_skills=["outer_outline_drawing"],
                completed_steps=["读取图纸", "提取外围轮廓"],
            ),
        )
        draft = self.store.create_from_task(task)
        self.assertEqual(draft.status, "draft")
        self.assertTrue(draft.review_required)
        self.assertEqual(draft.source_task_id, "task-1")
        self.assertEqual(draft.plan_steps, ["读取图纸", "提取外围轮廓"])
        self.assertEqual(self.store.get(draft.skill_id).source_trace_id, "trace-1")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["schema_version"], "1.0")

    def test_unregistered_tool_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the product whitelist"):
            self.store.create(
                SkillDraftCreateRequest(
                    name="危险草稿",
                    mcp_tools=["unregistered_write_tool"],
                )
            )

    def test_incomplete_task_cannot_be_converted(self):
        task = PlannerTaskDetailResponse(
            task_id="task-2",
            user_goal="未完成任务",
            task_status="waiting_user",
        )
        with self.assertRaisesRegex(ValueError, "only completed"):
            self.store.create_from_task(task)

    def test_draft_can_be_edited_validated_and_approved_without_being_enabled(self):
        draft = self.store.create(
            SkillDraftCreateRequest(
                name="外围轮廓流程",
                user_goal="绘制外围轮廓",
                plan_steps=["读取图纸"],
                mcp_tools=["get_drawing_snapshot"],
            )
        )
        updated = self.store.update(
            draft.skill_id,
            SkillDraftUpdateRequest(
                name="外围轮廓标准流程",
                user_goal="读取并提取外围轮廓",
                plan_steps=["读取图纸", "提取轮廓"],
                mcp_tools=["get_drawing_snapshot", "arch_extract_outer_outline"],
            ),
        )
        self.assertEqual(updated.version, 2)
        validated = self.store.validate(draft.skill_id)
        self.assertEqual(validated.status, "validated")
        self.assertEqual(validated.validation_errors, [])
        approved = self.store.approve(
            draft.skill_id,
            SkillDraftApprovalRequest(reviewer="CAD 管理员", review_note="已核对工具范围"),
        )
        self.assertEqual(approved.status, "approved")
        self.assertFalse(approved.review_required)
        self.assertFalse(approved.enabled)
        self.assertEqual(approved.reviewer, "CAD 管理员")

    def test_invalid_draft_cannot_be_approved(self):
        draft = self.store.create(SkillDraftCreateRequest(name="空流程"))
        validated = self.store.validate(draft.skill_id)
        self.assertEqual(validated.status, "draft")
        self.assertGreater(len(validated.validation_errors), 0)
        with self.assertRaisesRegex(ValueError, "pass validation"):
            self.store.approve(draft.skill_id, SkillDraftApprovalRequest(reviewer="reviewer"))


if __name__ == "__main__":
    unittest.main()
