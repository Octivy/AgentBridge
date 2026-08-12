import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smoke_test_mcp import parse_result, validate_result_protocol


def standard_payload(**overrides):
    payload = {
        "ok": True,
        "tool_name": "draw_line",
        "summary": "dry_run preview ready",
        "data": {"dry_run": True, "command_count": 1},
        "error_code": None,
        "error_message": None,
        "dry_run": True,
        "request_id": "req-123",
        "affected_entities_count": 0,
    }
    payload.update(overrides)
    return payload


class McpSmokeValidationTests(unittest.TestCase):
    def test_validate_result_protocol_accepts_standard_write_preview(self) -> None:
        errors = validate_result_protocol(
            standard_payload(),
            expected_tool_name="draw_line",
            expected_dry_run=True,
        )

        self.assertEqual(errors, [])

    def test_validate_result_protocol_rejects_missing_required_fields(self) -> None:
        payload = standard_payload()
        del payload["request_id"]

        errors = validate_result_protocol(
            payload,
            expected_tool_name="draw_line",
            expected_dry_run=True,
        )

        self.assertIn("missing required fields: request_id", errors)

    def test_validate_result_protocol_rejects_extra_fields(self) -> None:
        errors = validate_result_protocol(
            standard_payload(legacy_result={}),
            expected_tool_name="draw_line",
            expected_dry_run=True,
        )

        self.assertIn("unexpected fields: legacy_result", errors)

    def test_validate_result_protocol_rejects_dry_run_mismatch(self) -> None:
        errors = validate_result_protocol(
            standard_payload(dry_run=False),
            expected_tool_name="draw_line",
            expected_dry_run=True,
        )

        self.assertIn("dry_run mismatch: expected True, got False", errors)

    def test_validate_result_protocol_requires_error_fields_for_failures(self) -> None:
        errors = validate_result_protocol(
            standard_payload(ok=False, error_code=None, error_message=None),
            expected_tool_name="draw_line",
            expected_dry_run=True,
        )

        self.assertIn("failed results must include error_code", errors)
        self.assertIn("failed results must include error_message", errors)

    def test_parse_result_returns_standard_error_for_invalid_json(self) -> None:
        payload = parse_result("not-json")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["tool_name"], "unknown")
        self.assertEqual(payload["error_code"], "invalid_json")
        self.assertIn("Non-JSON tool result", payload["error_message"])


if __name__ == "__main__":
    unittest.main()
