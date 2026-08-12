import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.security_policy import evaluate_commit_policy


class SecurityPolicyTests(unittest.TestCase):
    def test_reversible_write_requires_no_extra_local_confirmation(self) -> None:
        self.assertTrue(
            evaluate_commit_policy(
                "reversible_write", confirmed_by_local_user=False, task_id=""
            ).allowed
        )

    def test_destructive_write_requires_local_confirmation(self) -> None:
        denied = evaluate_commit_policy(
            "destructive_write", confirmed_by_local_user=False, task_id="task-1"
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.error_code, "local_confirmation_required")
        self.assertTrue(
            evaluate_commit_policy(
                "destructive_write", confirmed_by_local_user=True, task_id="task-1"
            ).allowed
        )

    def test_critical_write_requires_confirmation_and_task_context(self) -> None:
        denied = evaluate_commit_policy(
            "critical", confirmed_by_local_user=True, task_id=""
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.error_code, "task_context_required")

    def test_preview_only_cannot_commit(self) -> None:
        denied = evaluate_commit_policy(
            "preview_only", confirmed_by_local_user=True, task_id="task-1"
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.error_code, "write_not_allowed")


if __name__ == "__main__":
    unittest.main()
