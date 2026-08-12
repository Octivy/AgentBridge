import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.agent_service import PLANNER_DECISION_SYSTEM_PROMPT


class PlannerPromptContractTests(unittest.TestCase):
    def test_system_prompt_includes_skill_parameter_clarification_contract(self) -> None:
        self.assertIn("skill_parameters", PLANNER_DECISION_SYSTEM_PROMPT)
        self.assertIn("auto_tool_calls", PLANNER_DECISION_SYSTEM_PROMPT)
        self.assertIn("缺少图层名、尺寸、位置或内容", PLANNER_DECISION_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
