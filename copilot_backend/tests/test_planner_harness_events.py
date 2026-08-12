import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.runtime import PlannerRuntime
from planner.session import PlannerSession, PlannerSessionState


class PlannerHarnessEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_records_harness_events_for_tool_call(self):
        async def decision_provider(_model_input):
            return {
                "intent": "draw a line",
                "reasoning_summary": "Need draw_line",
                "next_action": "call_tool",
                "tool_calls": [
                    {
                        "tool_name": "draw_line",
                        "arguments": {"start": [0, 0], "end": [10, 0]},
                    }
                ],
                "selected_skills": [],
                "completion_check": False,
                "user_message": "准备绘制直线。",
                "ask_user_type": "",
                "ask_user_hint": "",
                "suggested_steps": ["绘制直线"],
            }

        async def tool_executor(tool_name, arguments, dry_run):
            return {
                "ok": True,
                "tool_name": tool_name,
                "summary": "preview ready",
                "dry_run": dry_run,
                "data": {"command_count": 1},
            }

        session = PlannerSession(PlannerSessionState(session_id="task_1", user_goal="draw line"))
        runtime = PlannerRuntime(decision_provider=decision_provider, tool_executor=tool_executor)

        await runtime.run_until_pause_or_completion(session)

        event_types = [
            event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
            for event in session.state.harness_events
        ]
        self.assertIn("plan_created", event_types)
        self.assertIn("tool_requested", event_types)
        self.assertIn("tool_started", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("permission_requested", event_types)


if __name__ == "__main__":
    unittest.main()
