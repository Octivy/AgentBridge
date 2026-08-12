import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.runtime import PlannerRuntime
from planner.session import PlannerSession, PlannerSessionState, ToolCallSpec


class PlannerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_skills_expand_into_safe_tool_calls(self) -> None:
        decision_count = 0

        async def provider(_):
            nonlocal decision_count
            decision_count += 1
            if decision_count > 1:
                return json.dumps(
                    {
                        "intent": "drawing state read complete",
                        "reasoning_summary": "read-only analysis complete",
                        "next_action": "finish",
                        "tool_calls": [],
                        "selected_skills": ["drawing_snapshot_analysis"],
                        "completion_check": False,
                        "user_message": "drawing state has been analyzed",
                        "ask_user_type": "none",
                        "ask_user_hint": "",
                        "suggested_steps": ["inspect drawing"],
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "intent": "analyze drawing first",
                    "reasoning_summary": "use the drawing snapshot analysis skill",
                    "next_action": "call_tool",
                    "tool_calls": [],
                    "selected_skills": ["drawing_snapshot_analysis"],
                    "completion_check": False,
                    "user_message": "inspect the current drawing first",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["inspect drawing"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": f"{name} ok",
                "data": {},
                "request_id": f"req-{name}",
                "affected_entities_count": 0,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s1", user_goal="analyze drawing"))

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual([name for name, _, _ in executed], ["get_drawing_snapshot"])
        self.assertEqual(result.selected_skills, ["drawing_snapshot_analysis"])
        self.assertEqual(result.executed_tools, ["get_drawing_snapshot"])
        self.assertEqual(result.task_status, "completed")
        self.assertEqual(result.execution_events[0].request_id, "req-get_drawing_snapshot")
        self.assertEqual(session.state.execution_events[0].request_id, "req-get_drawing_snapshot")
        self.assertEqual([dry_run for _, _, dry_run in executed], [False])

    async def test_high_side_effect_tools_pause_after_dry_run_preview(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "draw one line",
                    "reasoning_summary": "preview the write before drawing",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "draw_line",
                            "arguments": {
                                "start": [0, 0],
                                "end": [100, 0],
                                "layer": "0",
                            },
                        }
                    ],
                    "selected_skills": [],
                    "completion_check": True,
                    "user_message": "draw a line",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["draw line preview"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": "dry_run preview ready",
                "data": {"dry_run": dry_run, "command_count": 1},
                "dry_run": dry_run,
                "request_id": "req-preview",
                "affected_entities_count": 0,
                "permission_request_id": "perm-preview",
                "permission_token": "signed-preview-ticket",
                "preview_hash": "abc123",
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s2", user_goal="draw line"))

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual(result.task_status, "waiting_user")
        self.assertEqual(len(executed), 1)
        self.assertTrue(executed[0][2])
        self.assertEqual(result.ask_user_type, "confirm_write")
        self.assertEqual(len(session.state.pending_confirmation_tool_calls), 1)
        self.assertEqual(session.state.pending_confirmation_tool_calls[0].tool_name, "draw_line")
        self.assertEqual(
            session.state.pending_confirmation_tool_calls[0].arguments["permission_token"],
            "signed-preview-ticket",
        )
        self.assertEqual(session.state.pending_confirmation_tool_calls[0].arguments["preview_hash"], "abc123")
        self.assertIn("确认执行", result.ask_user_hint)
        self.assertEqual(result.execution_events[0].details.get("dry_run"), True)
        self.assertEqual(result.execution_events[0].details.get("data", {}).get("command_count"), 1)
        self.assertEqual(result.execution_events[0].details.get("audit", {}).get("task_id"), "s2")
        self.assertEqual(result.execution_events[0].details.get("audit", {}).get("side_effect_level"), "high")
        self.assertTrue(result.execution_events[0].details.get("audit", {}).get("confirmation_required"))
        self.assertFalse(result.execution_events[0].details.get("audit", {}).get("confirmed_by_local_user"))
        self.assertEqual(session.state.execution_events[0].details.get("dry_run"), True)

    async def test_execute_approval_runs_write_without_preview_pause(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "draw one line",
                    "reasoning_summary": "approval allows direct execution",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "draw_line",
                            "arguments": {"start": [0, 0], "end": [100, 0], "layer": "0"},
                        }
                    ],
                    "selected_skills": [],
                    "completion_check": True,
                    "user_message": "draw a line",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["draw line"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": "line drawn",
                "data": {"dry_run": dry_run, "command_count": 1},
                "dry_run": dry_run,
                "request_id": "req-direct",
                "affected_entities_count": 1,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s-direct", user_goal="draw line", agent_approval="execute"))

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual(result.task_status, "completed")
        self.assertEqual(len(executed), 2)
        self.assertTrue(executed[0][2])
        self.assertFalse(executed[1][2])
        self.assertEqual(session.state.pending_confirmation_tool_calls, [])
        self.assertEqual(result.execution_events[0].details.get("dry_run"), True)
        self.assertEqual(result.execution_events[1].details.get("dry_run"), False)
        self.assertFalse(result.execution_events[1].details.get("audit", {}).get("confirmation_required"))

    async def test_failed_preview_marks_task_failed(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "draw one line",
                    "reasoning_summary": "preview the write before drawing",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "draw_line",
                            "arguments": {
                                "start": [0, 0],
                                "end": [100, 0],
                            },
                        }
                    ],
                    "selected_skills": [],
                    "completion_check": True,
                    "user_message": "draw a line",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["draw line preview"],
                },
                ensure_ascii=False,
            )

        async def tool_executor(name, args, dry_run=False):
            return {
                "ok": False,
                "summary": "bridge unavailable",
                "data": None,
                "error_code": "cad_bridge_error",
                "error_message": "bridge unavailable",
                "dry_run": None,
                "request_id": None,
                "affected_entities_count": None,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s-preview-failed", user_goal="draw line"))

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual(result.task_status, "failed")
        self.assertIsNotNone(session.state.last_error)
        self.assertEqual(session.state.last_error.code, "cad_bridge_error")
        self.assertEqual(session.state.execution_events[0].status, "failed")
        self.assertEqual(session.state.pending_confirmation_tool_calls, [])

    async def test_disabled_annotation_skill_and_tool_are_rejected(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "add annotation",
                    "reasoning_summary": "use annotation skill and add text",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "add_text",
                            "arguments": {
                                "content": "ROOM A",
                                "position": [100, 200],
                                "height": 250,
                                "layer": "TEXT",
                            },
                        }
                    ],
                    "selected_skills": ["annotation_text"],
                    "completion_check": True,
                    "user_message": "add room label",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["prepare text layer", "preview annotation"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": f"{name} preview ready",
                "data": {"dry_run": dry_run, "command_count": 1},
                "dry_run": dry_run,
                "request_id": f"req-{name}",
                "affected_entities_count": 0,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s4", user_goal="add room label"))

        with self.assertRaisesRegex(ValueError, "Unsupported tool_name: add_text"):
            await runtime.run_until_pause_or_completion(session)

        self.assertEqual(executed, [])

    async def test_disabled_layer_management_skill_is_rejected(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "prepare drawing layers",
                    "reasoning_summary": "layer management skill matches but no layer name is available",
                    "next_action": "call_tool",
                    "tool_calls": [],
                    "selected_skills": ["layer_management"],
                    "completion_check": False,
                    "user_message": "prepare layers",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["collect target layer"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {"ok": True, "summary": "unexpected", "data": {}}

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s6", user_goal="整理图层"))

        with self.assertRaisesRegex(ValueError, "Unsupported skill_id: layer_management"):
            await runtime.run_until_pause_or_completion(session)

        self.assertEqual(executed, [])

    async def test_low_side_effect_write_tool_requires_preview_confirmation(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "prepare layer",
                    "reasoning_summary": "ensure target layer exists",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "ensure_layer",
                            "arguments": {"layer": "WALL", "color": 1},
                        }
                    ],
                    "selected_skills": [],
                    "completion_check": True,
                    "user_message": "prepare wall layer",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["preview layer setup"],
                },
                ensure_ascii=False,
            )

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": "layer preview ready",
                "data": {"dry_run": dry_run},
                "dry_run": dry_run,
                "request_id": "req-layer-preview",
                "affected_entities_count": 0,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s5", user_goal="prepare layer"))

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual(result.task_status, "waiting_user")
        self.assertEqual(len(executed), 1)
        self.assertTrue(executed[0][2])
        self.assertEqual(session.state.pending_confirmation_tool_calls[0].tool_name, "ensure_layer")
        self.assertEqual(result.ask_user_type, "confirm_write")

    async def test_independent_architecture_authoring_tool_is_rejected(self) -> None:
        async def provider(_):
            return json.dumps(
                {
                    "intent": "create room object",
                    "reasoning_summary": "preview architecture room object before writing",
                    "next_action": "call_tool",
                    "tool_calls": [
                        {
                            "tool_name": "arch_create_room",
                            "arguments": {
                                "name": "卧室",
                                "boundary": [[0, 0], [4, 0], [4, 4.5], [0, 4.5]],
                                "layer": "A-ROOM",
                            },
                        }
                    ],
                    "selected_skills": [],
                    "completion_check": True,
                    "user_message": "preview room object",
                    "ask_user_type": "none",
                    "ask_user_hint": "",
                    "suggested_steps": ["生成房间对象预览"],
                },
                ensure_ascii=False,
            )

        async def tool_executor(name, args, dry_run=False):
            return {
                "ok": True,
                "summary": "已生成房间对象预览：卧室，面积 18.00 m2。",
                "data": {
                    "dry_run": dry_run,
                    "object_type": "room",
                    "created_object_ids": ["room-1"],
                    "affected_entities_count": 4,
                    "preview": {
                        "object_type": "room",
                        "name": "卧室",
                        "area": 18.0,
                    },
                },
                "dry_run": dry_run,
                "request_id": "req-arch-room-preview",
                "affected_entities_count": 4,
            }

        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)
        session = PlannerSession(PlannerSessionState(session_id="s-arch-room", user_goal="create bedroom room object"))

        with self.assertRaisesRegex(ValueError, "Unsupported tool_name: arch_create_room"):
            await runtime.run_until_pause_or_completion(session)

    async def test_confirmation_executes_pending_write_without_replanning(self) -> None:
        provider_called = 0

        async def provider(_):
            nonlocal provider_called
            provider_called += 1
            return {}

        executed = []

        async def tool_executor(name, args, dry_run=False):
            executed.append((name, args, dry_run))
            return {
                "ok": True,
                "summary": "write completed",
                "data": {"dry_run": dry_run, "affected_entities_count": 1},
                "dry_run": dry_run,
                "request_id": "req-write",
                "affected_entities_count": 1,
            }

        state = PlannerSessionState(
            session_id="s3",
            user_goal="draw line",
            last_user_message="确认执行",
        )
        state.pending_confirmation_tool_calls = [
            ToolCallSpec(
                tool_name="draw_line",
                arguments={"start": [0, 0], "end": [200, 100], "layer": "0"},
            )
        ]
        session = PlannerSession(state)
        runtime = PlannerRuntime(decision_provider=provider, tool_executor=tool_executor)

        result = await runtime.run_until_pause_or_completion(session)

        self.assertEqual(provider_called, 0)
        self.assertEqual(result.task_status, "completed")
        self.assertEqual(len(executed), 1)
        self.assertFalse(executed[0][2])
        self.assertEqual(session.state.pending_confirmation_tool_calls, [])
        self.assertIn("Confirmed write completed", result.final_response)
        self.assertEqual(result.execution_events[0].details.get("affected_entities_count"), 1)
        self.assertEqual(result.execution_events[0].details.get("data", {}).get("affected_entities_count"), 1)
        self.assertEqual(executed[0][1]["task_id"], "s3")
        self.assertTrue(executed[0][1]["confirmed_by_local_user"])
        self.assertEqual(result.execution_events[0].details.get("audit", {}).get("task_id"), "s3")
        self.assertTrue(result.execution_events[0].details.get("audit", {}).get("confirmed_by_local_user"))
        self.assertEqual(result.execution_events[0].details.get("audit", {}).get("confirmation_source"), "local_user_message")


if __name__ == "__main__":
    unittest.main()
