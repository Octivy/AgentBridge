import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cadmcp.permission_ticket import PermissionTicketError, PermissionTicketService


class PermissionTicketServiceTests(unittest.TestCase):
    def test_ticket_is_bound_to_tool_arguments_and_is_one_time(self) -> None:
        service = PermissionTicketService(secret="test-secret", ttl_seconds=60)
        arguments = {"mappings": [{"source_layer": "WALL", "target_layer": "A-WALL"}]}
        grant = service.issue("arch_apply_layer_mapping", arguments, now=100)

        payload = service.consume(
            "arch_apply_layer_mapping",
            arguments,
            grant.permission_token,
            expected_preview_hash=grant.preview_hash,
            now=101,
        )
        self.assertEqual(payload["permission_request_id"], grant.permission_request_id)

        with self.assertRaisesRegex(PermissionTicketError, "already been used"):
            service.consume("arch_apply_layer_mapping", arguments, grant.permission_token, now=102)

    def test_ticket_rejects_tampering_and_expiry(self) -> None:
        service = PermissionTicketService(secret="test-secret", ttl_seconds=30)
        original = {"boundary": [[0, 0], [10, 0], [10, 10], [0, 10]]}
        changed = {"boundary": [[0, 0], [20, 0], [20, 10], [0, 10]]}
        grant = service.issue("arch_draw_outer_outline", original, now=100)

        with self.assertRaisesRegex(PermissionTicketError, "changed after preview"):
            service.consume("arch_draw_outer_outline", changed, grant.permission_token, now=101)

        expired = service.issue("arch_draw_outer_outline", original, now=100)
        with self.assertRaisesRegex(PermissionTicketError, "expired"):
            service.consume("arch_draw_outer_outline", original, expired.permission_token, now=131)


if __name__ == "__main__":
    unittest.main()
