import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from acceptance.runner import (
    AcceptanceCheck,
    AcceptanceReport,
    classify_error,
    safe_error,
    write_report,
)


class AcceptanceRunnerTests(unittest.TestCase):
    def test_error_classification(self):
        self.assertEqual(classify_error(RuntimeError("HTTP 401 invalid api key")), "authentication")
        self.assertEqual(classify_error(RuntimeError("request timed out")), "timeout")
        self.assertEqual(classify_error(RuntimeError("connection refused")), "unreachable")

    def test_report_is_machine_and_human_readable(self):
        report = AcceptanceReport(
            schema_version="1.0",
            generated_at="2026-07-24T00:00:00+00:00",
            status="blocked",
            checks=[
                AcceptanceCheck(
                    check_id="bridge",
                    name="Bridge",
                    status="blocked",
                    summary="not running",
                    recovery_action="start AutoCAD",
                )
            ],
            environment={"autocad_running": False},
        )
        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path = write_report(report, Path(directory))
            self.assertIn('"secrets_redacted": true', json_path.read_text(encoding="utf-8"))
            self.assertIn("start AutoCAD", markdown_path.read_text(encoding="utf-8"))

    def test_safe_error_never_returns_more_than_limit(self):
        self.assertLessEqual(len(safe_error(RuntimeError("x" * 1000))), 500)


if __name__ == "__main__":
    unittest.main()
