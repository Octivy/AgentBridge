import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from http_api.app import app
from shared.schemas import ChatMessageResponse, KnowledgeQueryResponse, SkillDraftResponse
from datetime import datetime, timezone


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_reports_cadmcp(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mcp_server"], "cadmcp")
        self.assertEqual(response.json()["connector"]["mcp"]["tool_count"], 13)

    def test_connector_capabilities_are_exposed(self):
        response = self.client.get("/connector/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mcp"]["tool_count"], 13)
        self.assertIn("openai_chat", response.json()["model_gateway"]["protocols"])

    def test_connector_diagnostics_are_exposed(self):
        health = {
            "ok": True,
            "result": {
                "bridge": {"protocol_version": "2.0", "auth_required": False},
                "autocad": {"document_open": False},
                "plugin": {"version": "0.9.0.622"},
            },
        }
        with patch(
            "connector_runtime.diagnostics.CadLocalBridgeClient.health",
            AsyncMock(return_value=health),
        ):
            response = self.client.get("/connector/diagnostics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["components"]), 5)

    def test_removed_product_platform_routes_are_not_exposed(self):
        for path in (
            "/auth/register",
            "/auth/login",
            "/product/session",
            "/product/credits",
            "/product/plans",
            "/deployment/snapshot",
            "/release/manifest",
            "/plugin/update/manifest",
            "/diagnostics/report",
            "/admin/users",
        ):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_chat_rejects_empty_request(self):
        response = self.client.post("/chat/message", json={"message": "", "mode": "chat"})
        self.assertEqual(response.status_code, 400)

    def test_standard_chat_uses_chat_handler(self):
        payload = ChatMessageResponse(reply_text="ok")
        with patch("http_api.routes.handle_standard_chat", AsyncMock(return_value=payload)) as handler:
            response = self.client.post("/chat/message", json={"message": "hello", "mode": "chat"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply_text"], "ok")
        self.assertNotIn("credit_usage", response.json())
        handler.assert_awaited_once()

    def test_draw_chat_uses_planner_handler(self):
        payload = ChatMessageResponse(reply_text="planned")
        with patch("http_api.routes.handle_agent_draw", AsyncMock(return_value=payload)) as handler:
            response = self.client.post("/chat/message", json={"message": "inspect", "mode": "draw"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply_text"], "planned")
        handler.assert_awaited_once()

    def test_grounded_knowledge_query_route(self):
        payload = KnowledgeQueryResponse(
            answer="规范回答 [S1]",
            grounded=True,
            trace_id="trace-knowledge",
        )
        with patch("http_api.routes.knowledge_query_service.query", AsyncMock(return_value=payload)) as query:
            response = self.client.post("/knowledge/query", json={"question": "防火规范是什么？"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["grounded"])
        query.assert_awaited_once()

    def test_product_skill_and_tool_lists_are_exact(self):
        skill_ids = {item["skill_id"] for item in self.client.get("/planner/skills").json()}
        tools = self.client.get("/planner/tools").json()
        tool_ids = {item["tool_name"] for item in tools}
        self.assertEqual(skill_ids, {"drawing_snapshot_analysis", "functional_object_recognition", "outer_outline_drawing", "layer_normalization"})
        self.assertEqual(len(tool_ids), 13)
        self.assertIn("arch_draw_outer_outline", tool_ids)
        self.assertNotIn("arch_create_wall", tool_ids)
        self.assertEqual(self.client.get("/planner/tools/arch_create_wall").status_code, 404)

    def test_unknown_task_returns_404(self):
        with patch("http_api.routes.planner_agent_service.get_task", Mock(return_value=None)):
            response = self.client.get("/planner/tasks/missing")
        self.assertEqual(response.status_code, 404)

    def test_completed_task_can_create_review_only_skill_draft(self):
        draft = SkillDraftResponse(
            skill_id="sample-12345678",
            name="sample",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with (
            patch("http_api.routes.planner_agent_service.get_task", Mock(return_value=Mock(task_status="completed"))) as get_task,
            patch("http_api.routes.skill_draft_store.create_from_task", Mock(return_value=draft)) as create,
        ):
            response = self.client.post("/planner/tasks/task-1/skill-draft")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["review_required"])
        get_task.assert_called_once_with("task-1")
        create.assert_called_once()

    def test_task_list_passes_filter(self):
        with patch("http_api.routes.planner_agent_service.list_recent_tasks", Mock(return_value=[])) as list_tasks:
            response = self.client.get("/planner/tasks?limit=5&status=failed")
        self.assertEqual(response.status_code, 200)
        list_tasks.assert_called_once_with(limit=5, status_filter="failed")

    def test_config_routes_remain_available(self):
        self.assertEqual(self.client.get("/config/snapshot").status_code, 200)
        self.assertEqual(self.client.get("/config/validate").status_code, 200)


if __name__ == "__main__":
    unittest.main()
