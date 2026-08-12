import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.prompt_builder import PlannerPromptBuilder
from planner.session import PlannerSessionState
from skills.registry import get_skill


class PlannerPromptBuilderTests(unittest.TestCase):
    def test_available_skills_only_include_enabled_product_skills(self) -> None:
        payload = PlannerPromptBuilder().build(
            PlannerSessionState(session_id="s1", user_goal="understand the drawing")
        )

        skill_ids = {skill["skill_id"] for skill in payload["available_skills"]}
        self.assertEqual(
            skill_ids,
            {
                "drawing_snapshot_analysis",
                "functional_object_recognition",
                "outer_outline_drawing",
                "layer_normalization",
            },
        )
        self.assertNotIn("annotation_text", skill_ids)
        self.assertNotIn("architecture_wall_opening", skill_ids)

    def test_available_tools_exclude_independent_authoring_tools(self) -> None:
        payload = PlannerPromptBuilder().build(
            PlannerSessionState(session_id="s2", user_goal="inspect product tool surface")
        )

        tool_ids = {tool["tool_name"] for tool in payload["available_tools"]}
        self.assertIn("get_drawing_snapshot", tool_ids)
        self.assertNotIn("arch_create_wall", tool_ids)
        self.assertNotIn("arch_create_room", tool_ids)

    def test_all_available_skills_include_acceptance_examples(self) -> None:
        payload = PlannerPromptBuilder().build(
            PlannerSessionState(session_id="s3", user_goal="review skill coverage")
        )

        for skill in payload["available_skills"]:
            self.assertGreater(len(skill["acceptance_examples"]), 0, skill["skill_id"])
            self.assertTrue(skill["acceptance_examples"][0]["title"])
            self.assertTrue(skill["acceptance_examples"][0]["expected_behavior"])

    def test_first_stage_skill_nodes_are_registered(self) -> None:
        expected = {
            "drawing_snapshot_analysis": True,
            "functional_object_recognition": True,
            "outer_outline_drawing": True,
            "layer_normalization": True,
        }

        for skill_id, enabled in expected.items():
            with self.subTest(skill_id=skill_id):
                skill = get_skill(skill_id)
                self.assertIsNotNone(skill)
                self.assertEqual(skill.enabled, enabled)


if __name__ == "__main__":
    unittest.main()
