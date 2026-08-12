import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_runtime.result_protocol import STANDARD_TOOL_RESULT_SCHEMA, build_tool_error_result, normalize_tool_result


class ToolResultProtocolTests(unittest.TestCase):
    def test_normalize_successful_snapshot_result(self) -> None:
        payload = {
            "ok": True,
            "tool_name": "get_drawing_snapshot",
            "result": {
                "entity_count": 42,
                "layer_count": 5,
                "json_size": 1024,
            },
        }

        normalized = normalize_tool_result("get_drawing_snapshot", payload)

        self.assertTrue(normalized["ok"])
        self.assertEqual(normalized["tool_name"], "get_drawing_snapshot")
        self.assertEqual(normalized["data"]["entity_count"], 42)
        self.assertEqual(normalized["summary"], "已读取 5 个图层。")
        self.assertIsNone(normalized["error_code"])
        self.assertIsNone(normalized["error_message"])
        self.assertIsNone(normalized["dry_run"])
        self.assertIsNone(normalized["request_id"])
        self.assertIsNone(normalized["affected_entities_count"])

    def test_normalize_write_result_preserves_dry_run(self) -> None:
        payload = {
            "ok": True,
            "tool_name": "draw_line",
            "result": {
                "dry_run": True,
                "command_count": 1,
            },
            "execution_log": ["Dry run only. No CAD entities were created."],
        }

        normalized = normalize_tool_result("draw_line", payload)

        self.assertTrue(normalized["ok"])
        self.assertTrue(normalized["dry_run"])
        self.assertEqual(normalized["summary"], "已验证 1 条待应用命令。")
        self.assertIsNone(normalized["request_id"])
        self.assertIsNone(normalized["affected_entities_count"])

    def test_normalize_dry_run_write_result_adds_harness_fields(self) -> None:
        normalized = normalize_tool_result(
            "draw_line",
            {
                "ok": True,
                "summary": "preview ready",
                "dry_run": True,
                "data": {"command_count": 1},
            },
        )

        self.assertTrue(normalized["ok"])
        self.assertEqual(normalized["tool_name"], "draw_line")
        self.assertEqual(normalized["summary"], "preview ready")
        self.assertTrue(normalized["dry_run"])
        self.assertEqual(normalized["risk_level"], "reversible_write")
        self.assertTrue(normalized["requires_permission"])
        self.assertEqual(normalized["next_action"]["type"], "ask_permission")
        self.assertEqual(normalized["preview"]["kind"], "cad_diff")
        self.assertIsNone(normalized["transaction"]["transaction_id"])

    def test_normalize_result_preserves_request_id_and_affected_entities_count(self) -> None:
        payload = {
            "ok": True,
            "tool_name": "draw_line",
            "request_id": "req-123",
            "affected_entities_count": 1,
            "result": {
                "dry_run": False,
                "affected_entities_count": 1,
            },
        }

        normalized = normalize_tool_result("draw_line", payload)

        self.assertEqual(normalized["request_id"], "req-123")
        self.assertEqual(normalized["affected_entities_count"], 1)

    def test_build_tool_error_result_uses_standard_shape(self) -> None:
        normalized = build_tool_error_result("list_layers", "cad_bridge_error", "bridge unavailable")

        self.assertEqual(
            normalized,
            {
                "ok": False,
                "tool_name": "list_layers",
                "summary": "bridge unavailable",
                "data": None,
                "error_code": "cad_bridge_error",
                "error_message": "bridge unavailable",
                "dry_run": None,
                "request_id": None,
                "affected_entities_count": None,
            },
        )

    def test_standard_schema_declares_required_fields(self) -> None:
        self.assertIn("required", STANDARD_TOOL_RESULT_SCHEMA)
        self.assertEqual(
            STANDARD_TOOL_RESULT_SCHEMA["required"],
            ["ok", "tool_name", "summary", "data", "error_code", "error_message", "dry_run", "request_id", "affected_entities_count"],
        )


if __name__ == "__main__":
    unittest.main()
