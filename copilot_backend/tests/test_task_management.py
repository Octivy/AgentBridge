import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.agent_service import PlannerAgentService
from planner.memory_store import InMemoryPlannerStore
from planner.persistent_store import JsonPlannerStore
from planner.session import PlannerActionType, PlannerDecision, PlannerExecutionEventRecord
from planner.task_service import PlannerTaskService
from shared.schemas import PlannerTaskLocalResultRequest, PlannerTaskPermissionDecisionRequest
from shared.schemas import ChatMessageRequest


class FakeGatewayService:
    async def request_text(self, *_args, **_kwargs) -> str:
        raise AssertionError("deterministic geometry fallback should not call the model")


class CapturingGatewayService:
    def __init__(self) -> None:
        self.prompts = []

    async def request_text(self, _request, _system_prompt, prompt) -> str:
        self.prompts.append(prompt)
        return (
            '{"intent":"ask","reasoning_summary":"need more info","next_action":"ask_user",'
            '"tool_calls":[],"selected_skills":[],"completion_check":false,'
            '"user_message":"请补充尺寸","ask_user_type":"missing_dimension",'
            '"ask_user_hint":"请补充尺寸","suggested_steps":["确认尺寸"]}'
        )


class FakeToolExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def execute_tool(self, tool_name, arguments, *, caller="planner_runtime", timeout_ms=30000, dry_run=False):
        self.calls.append((tool_name, arguments, dry_run))
        data = {
            "dry_run": dry_run,
            "command_count": len(arguments.get("commands", [])) if isinstance(arguments, dict) else 0,
        }
        return {
            "ok": True,
            "tool_name": tool_name,
            "summary": f"{tool_name} preview ready",
            "data": data,
            "dry_run": dry_run,
            "request_id": f"req-{tool_name}",
            "affected_entities_count": 0,
        }


class PlannerTaskManagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = InMemoryPlannerStore()
        self.task_service = PlannerTaskService(store=self.store)
        self.agent_service = PlannerAgentService(store=self.store, task_service=self.task_service)

    def test_list_recent_tasks_uses_updated_time_and_exposes_ui_flags(self) -> None:
        older = self.task_service.create_task(user_goal="older task", last_user_message="draw a line")
        older.state.completed_steps.append("inspect drawing")
        self.task_service.save_task(older)

        newer = self.task_service.create_task(user_goal="newer task", last_user_message="provide dimensions")
        newer.wait_for_user("please provide dimensions")
        newer.state.pending_steps = ["provide dimensions"]
        self.task_service.save_task(newer)

        older.fail("local bridge unavailable", error_code="bridge_unavailable", technical_detail="bridge timeout")
        self.task_service.save_task(older)

        summaries = self.task_service.list_recent_tasks(limit=2)

        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0].task_id, older.state.session_id)
        self.assertTrue(summaries[0].retryable)
        self.assertFalse(summaries[0].resumable)
        self.assertFalse(summaries[0].cancellable)
        self.assertEqual(summaries[0].active_step, "inspect drawing")
        self.assertIsNotNone(summaries[0].created_at)
        self.assertIsNotNone(summaries[0].updated_at)
        self.assertIsNotNone(summaries[0].last_error)
        self.assertEqual(summaries[0].last_error.code, "bridge_unavailable")

        self.assertEqual(summaries[1].task_id, newer.state.session_id)
        self.assertFalse(summaries[1].retryable)
        self.assertTrue(summaries[1].resumable)
        self.assertTrue(summaries[1].cancellable)
        self.assertEqual(summaries[1].active_step, "provide dimensions")
        self.assertIsNone(summaries[1].last_error)

    def test_json_planner_store_persists_and_reloads_task_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "planner-tasks.json"
            persistent_store = JsonPlannerStore(store_path)
            task_service = PlannerTaskService(store=persistent_store)
            session = task_service.create_task(
                user_goal="persist task",
                last_user_message="draw persisted line",
                trace_id="trace-persist",
            )
            session.state.execution_events.append(
                PlannerExecutionEventRecord(
                    tool_name="draw_line",
                    status="succeeded",
                    summary="line preview ready",
                    request_id="req-persist",
                    trace_id="trace-persist",
                    details={"dry_run": True},
                )
            )
            session.wait_for_user("confirm write")
            task_service.save_task(session)

            reloaded_store = JsonPlannerStore(store_path)
            reloaded = reloaded_store.get(session.state.session_id)

            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.state.trace_id, "trace-persist")
            self.assertEqual(reloaded.state.task_status.value, "waiting_user")
            self.assertEqual(reloaded.state.execution_events[0].request_id, "req-persist")
            self.assertEqual(reloaded.state.execution_events[0].details["dry_run"], True)

            reloaded_store.delete(session.state.session_id)
            self.assertIsNone(JsonPlannerStore(store_path).get(session.state.session_id))

    def test_list_recent_tasks_supports_status_filter(self) -> None:
        completed = self.task_service.create_task(user_goal="completed task", last_user_message="done")
        completed.complete("task completed")
        self.task_service.save_task(completed)

        failed = self.task_service.create_task(user_goal="failed task", last_user_message="retry")
        failed.fail("bridge error", error_code="bridge_error")
        self.task_service.save_task(failed)

        waiting = self.task_service.create_task(user_goal="waiting task", last_user_message="continue")
        waiting.wait_for_user("please continue with more details")
        self.task_service.save_task(waiting)

        active = self.task_service.list_recent_tasks(limit=10, status_filter="active")
        failed_only = self.task_service.list_recent_tasks(limit=10, status_filter="failed")

        self.assertEqual([task.task_id for task in active], [waiting.state.session_id])
        self.assertEqual([task.task_id for task in failed_only], [failed.state.session_id])

    def test_get_task_detail_includes_last_error_and_task_actions(self) -> None:
        session = self.task_service.create_task(user_goal="draw room", last_user_message="draw a room outline")
        session.fail(
            "Planner runtime failed. Check backend or tool bridge state and retry.",
            error_code="planner_runtime_failed",
            technical_detail="tool executor unavailable",
        )
        self.task_service.save_task(session)

        detail = self.agent_service.get_task(session.state.session_id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.task_status, "failed")
        self.assertFalse(detail.resumable)
        self.assertTrue(detail.retryable)
        self.assertFalse(detail.cancellable)
        self.assertIsNotNone(detail.last_error)
        self.assertEqual(detail.last_error.code, "planner_runtime_failed")
        self.assertIn("Check backend or tool bridge state", detail.last_error.message)
        self.assertEqual(detail.last_error.technical_detail, "tool executor unavailable")
        self.assertIsNotNone(detail.created_at)
        self.assertIsNotNone(detail.updated_at)

    def test_get_task_detail_preserves_execution_event_details_for_preview_ui(self) -> None:
        session = self.task_service.create_task(user_goal="draw line", last_user_message="draw a line")
        session.state.last_model_decision = PlannerDecision(
            intent="preview write",
            reasoning_summary="dry_run before write",
            next_action=PlannerActionType.CALL_TOOL,
            ask_user_type="confirm_write",
            ask_user_hint="已生成更改预览。点击“应用到图纸”或回复“确认执行”后，我会把更改应用到当前图纸。",
        )
        session.wait_for_user_with_hint(
            "已生成更改预览。点击“应用到图纸”或回复“确认执行”后，我会把更改应用到当前图纸。",
            ask_user_type="confirm_write",
            ask_user_hint="已生成更改预览。点击“应用到图纸”或回复“确认执行”后，我会把更改应用到当前图纸。",
        )
        session.state.execution_events.append(
            PlannerExecutionEventRecord(
                tool_name="draw_line",
                status="succeeded",
                summary="dry_run preview ready",
                request_id="req-preview",
                details={
                    "dry_run": True,
                    "data": {
                        "command_count": 1,
                        "commands": [
                            {
                                "type": "LINE",
                                "start": [0, 0],
                                "end": [100, 0],
                                "layer": "0",
                            }
                        ],
                    },
                },
            )
        )
        self.task_service.save_task(session)

        detail = self.agent_service.get_task(session.state.session_id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.planner_state.ask_user_type, "confirm_write")
        self.assertEqual(len(detail.planner_state.execution_events), 1)
        event = detail.planner_state.execution_events[0]
        self.assertEqual(event.request_id, "req-preview")
        self.assertEqual(event.details["dry_run"], True)
        self.assertEqual(event.details["data"]["command_count"], 1)
        self.assertEqual(event.details["data"]["commands"][0]["type"], "LINE")

    async def test_nested_geometry_request_uses_deterministic_batch_preview(self) -> None:
        tool_executor = FakeToolExecutor()
        service = PlannerAgentService(
            store=InMemoryPlannerStore(),
            gateway_service=FakeGatewayService(),
            tool_executor=tool_executor,
        )
        trace_id = "trace-nested-geometry"

        response = await service.run_draw_request(
            ChatMessageRequest(
                message="在原点，绘制一个半径36米的圆，然后在圆内画一个最大的矩形，然后在矩形内画一个最大的圆，然后在圆中绘制一个最大的正方形，标注正方形面积",
                mode="draw",
                trace_id=trace_id,
            )
        )

        self.assertEqual(response.task_status, "waiting_user")
        self.assertEqual(response.trace_id, trace_id)
        self.assertEqual(response.planner_state.trace_id, trace_id)
        self.assertEqual(response.ask_user_type, "confirm_write")
        self.assertEqual(response.selected_skills, [])
        self.assertEqual([call[0] for call in tool_executor.calls], ["execute_draw_batch"])
        self.assertEqual([call[2] for call in tool_executor.calls], [True])

        batch_arguments = tool_executor.calls[0][1]
        self.assertEqual(batch_arguments["trace_id"], trace_id)
        self.assertEqual(len(batch_arguments["commands"]), 5)
        self.assertEqual([command["type"] for command in batch_arguments["commands"]], ["CIRCLE", "RECTANGLE", "CIRCLE", "POLYLINE", "TEXT"])
        self.assertEqual(batch_arguments["commands"][0]["radius"], 36.0)
        self.assertAlmostEqual(batch_arguments["commands"][1]["end"][0], 25.4558)
        self.assertAlmostEqual(batch_arguments["commands"][3]["points"][1][0], 18.0)
        self.assertIn("1296", batch_arguments["commands"][4]["content"])
        self.assertEqual(response.execution_events[0].trace_id, trace_id)

        detail = service.get_task(response.planner_session_id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.trace_id, trace_id)
        self.assertEqual(detail.planner_state.execution_events[0].trace_id, trace_id)

    async def test_local_cad_result_marks_waiting_task_completed(self) -> None:
        tool_executor = FakeToolExecutor()
        service = PlannerAgentService(
            store=InMemoryPlannerStore(),
            gateway_service=FakeGatewayService(),
            tool_executor=tool_executor,
        )

        response = await service.run_draw_request(
            ChatMessageRequest(
                message="在原点，绘制一个半径36米的圆，然后在圆内画一个最大的矩形，然后在矩形内画一个最大的圆，然后在圆中绘制一个最大的正方形，标注正方形面积",
                mode="draw",
                trace_id="trace-local-complete",
            )
        )
        self.assertEqual(response.task_status, "waiting_user")

        detail = service.record_local_result(
            response.planner_session_id,
            PlannerTaskLocalResultRequest(
                status="completed",
                message="本地 AutoCAD 已应用预览命令",
                affected_entities_count=5,
                trace_id="trace-local-complete",
            ),
        )

        self.assertIsNotNone(detail)
        self.assertEqual(detail.task_status, "completed")
        self.assertFalse(detail.resumable)
        self.assertEqual(detail.planner_state.pending_steps, [])
        self.assertTrue(detail.planner_state.execution_events)
        self.assertEqual(detail.planner_state.execution_events[-1].tool_name, "local_apply_preview")
        self.assertEqual(detail.planner_state.execution_events[-1].details["affected_entities_count"], 5)

    async def test_local_cad_result_records_transaction_harness_events(self) -> None:
        service = PlannerAgentService(
            store=InMemoryPlannerStore(),
            gateway_service=FakeGatewayService(),
            tool_executor=FakeToolExecutor(),
        )

        response = await service.run_draw_request(
            ChatMessageRequest(
                message="在原点，绘制一个半径36米的圆，然后在圆内画一个最大的矩形，然后在矩形内画一个最大的圆，然后在圆中绘制一个最大的正方形，标注正方形面积",
                mode="draw",
                trace_id="trace-local-transaction",
            )
        )
        self.assertEqual(response.task_status, "waiting_user")

        detail = service.record_local_result(
            response.planner_session_id,
            PlannerTaskLocalResultRequest(
                status="completed",
                message="Local CAD write completed.",
                affected_entities_count=2,
                trace_id="trace-local-transaction",
                details={
                    "transaction": {
                        "transaction_id": "cadtx_test",
                        "undo_group": "CADCOPILOT_TASK_test",
                        "rollback_token": "cadtx_test",
                        "rollback_supported": True,
                    },
                    "affected_entities": [
                        {"operation": "created", "type": "circle", "layer": "AI_GEOMETRY"},
                        {"operation": "created", "type": "text", "layer": "TEXT"},
                    ],
                },
            ),
        )

        self.assertIsNotNone(detail)
        events_response = service.get_task_events(response.planner_session_id)
        self.assertIsNotNone(events_response)
        event_types = [event.event_type for event in events_response.events]
        self.assertIn("cad_transaction_started", event_types)
        self.assertIn("cad_write_applied", event_types)
        applied_event = next(event for event in events_response.events if event.event_type == "cad_write_applied")
        self.assertEqual(applied_event.payload["transaction"]["transaction_id"], "cadtx_test")
        self.assertEqual(applied_event.payload["affected_entities_count"], 2)

    async def test_permission_denial_cancels_waiting_write_task_with_audit_event(self) -> None:
        service = PlannerAgentService(
            store=InMemoryPlannerStore(),
            gateway_service=FakeGatewayService(),
            tool_executor=FakeToolExecutor(),
        )

        response = await service.run_draw_request(
            ChatMessageRequest(
                message="在原点，绘制一个半径36米的圆，然后在圆内绘制一个最大的长方形，并标注面积",
                mode="draw",
                trace_id="trace-deny-write",
            )
        )
        self.assertEqual(response.task_status, "waiting_user")
        self.assertEqual(response.planner_state.agent_approval, "annotate")
        self.assertEqual(response.planner_state.pending_permission_action, "confirm_write")

        detail = service.record_permission_decision(
            response.planner_session_id,
            PlannerTaskPermissionDecisionRequest(
                decision="deny",
                message="Do not write these changes.",
                trace_id="trace-deny-write",
            ),
        )

        self.assertIsNotNone(detail)
        self.assertEqual(detail.task_status, "cancelled")
        self.assertFalse(detail.resumable)
        self.assertTrue(detail.planner_state.execution_events)
        event = detail.planner_state.execution_events[-1]
        self.assertEqual(event.tool_name, "permission_decision")
        self.assertEqual(event.status, "cancelled")
        self.assertEqual(event.details["decision"], "deny")
        self.assertEqual(event.details["audit"]["confirmation_required"], True)
        self.assertEqual(event.details["audit"]["confirmed_by_local_user"], False)

    async def test_agent_approval_is_added_to_planner_prompt(self) -> None:
        gateway = CapturingGatewayService()
        service = PlannerAgentService(
            store=InMemoryPlannerStore(),
            gateway_service=gateway,
            tool_executor=FakeToolExecutor(),
        )

        response = await service.run_draw_request(
            ChatMessageRequest(
                message="请检查当前图纸并整理图层",
                mode="draw",
                agent_approval="execute",
                trace_id="trace-approval",
            )
        )

        self.assertEqual(response.task_status, "waiting_user")
        self.assertTrue(gateway.prompts)
        self.assertIn("AgentApproval: execute", gateway.prompts[0])
        self.assertIn("权限策略：替我执行", gateway.prompts[0])


if __name__ == "__main__":
    unittest.main()
