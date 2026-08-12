import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cadmcp.permission_ticket import PermissionTicketService
from cadmcp.tool_executor import CadToolExecutor


class FakeCadBridgeClient:
    def __init__(self) -> None:
        self.health_called = False
        self.execute_calls = []

    async def health(self):
        self.health_called = True
        return {"ok": True, "tool_name": "cad_health_check", "result": {"bridge": {"enabled": True}}}

    async def execute_tool(
        self, tool_name, arguments, *, caller="mcp_server", timeout_ms=30000, dry_run=False, trace_id=""
    ):
        self.execute_calls.append(
            {"tool_name": tool_name, "arguments": dict(arguments), "caller": caller,
             "timeout_ms": timeout_ms, "dry_run": dry_run, "trace_id": trace_id}
        )
        if tool_name == "get_drawing_snapshot":
            return {
                "ok": True,
                "tool_name": tool_name,
                "result": {"snapshot": sample_snapshot()},
                "affected_entities_count": 0,
            }
        return {
            "ok": True,
            "tool_name": tool_name,
            "result": {
                "dry_run": dry_run,
                "verified": not dry_run,
                "affected_entities_count": 0 if dry_run else 1,
                "entity_handles": [] if dry_run else ["A1"],
                "transaction": {
                    "transaction_id": "cadtx-test",
                    "rollback_token": "cadrb-test",
                    "rollback_supported": True,
                },
            },
            "affected_entities_count": 0 if dry_run else 1,
        }


def sample_snapshot():
    return {
        "drawing_summary": {"total_entities": 4, "bounds": {"min": [0, 0], "max": [100, 100]}},
        "layers": [{"name": "WALL", "count": 4, "types": ["Line"]}],
        "entities": [
            {"handle": "1", "type": "Line", "layer": "WALL", "start": [0, 0], "end": [100, 0]},
            {"handle": "2", "type": "Line", "layer": "WALL", "start": [100, 0], "end": [100, 100]},
            {"handle": "3", "type": "Line", "layer": "WALL", "start": [100, 100], "end": [0, 100]},
            {"handle": "4", "type": "Line", "layer": "WALL", "start": [0, 100], "end": [0, 0]},
        ],
        "blocks": [], "texts": [], "dimensions": [],
    }


class CadToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    def build_executor(self):
        bridge = FakeCadBridgeClient()
        executor = CadToolExecutor(
            cad_bridge_client=bridge,
            permission_service=PermissionTicketService(secret="unit-test", ttl_seconds=60),
        )
        return executor, bridge

    async def test_health_uses_local_bridge(self):
        executor, bridge = self.build_executor()
        result = await executor.execute_tool("cad_health_check")
        self.assertTrue(result["ok"])
        self.assertTrue(bridge.health_called)

    async def test_read_tool_injects_current_snapshot(self):
        executor, bridge = self.build_executor()
        result = await executor.execute_tool("arch_recognize_functional_objects")
        self.assertTrue(result["ok"])
        self.assertEqual(bridge.execute_calls[0]["tool_name"], "get_drawing_snapshot")
        self.assertGreaterEqual(result["data"]["summary"]["semantic_counts"]["wall"], 1)

    async def test_outline_preview_is_local_and_issues_ticket(self):
        executor, bridge = self.build_executor()
        result = await executor.execute_tool(
            "arch_draw_outer_outline",
            {"boundary": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            dry_run=True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["requires_permission"])
        self.assertTrue(result["permission_token"])
        self.assertEqual(bridge.execute_calls, [])
        self.assertEqual(result["data"]["preview"]["command_count"], 1)

    async def test_outline_commit_consumes_ticket_and_requires_bridge_verification(self):
        executor, bridge = self.build_executor()
        arguments = {"boundary": [[0, 0], [100, 0], [100, 100], [0, 100]]}
        preview = await executor.execute_tool("arch_draw_outer_outline", arguments, dry_run=True)
        commit = await executor.execute_tool(
            "arch_draw_outer_outline",
            {**arguments, "permission_token": preview["permission_token"],
             "preview_hash": preview["preview_hash"]},
            dry_run=False,
        )
        self.assertTrue(commit["ok"])
        self.assertTrue(commit["data"]["verified"])
        self.assertEqual(bridge.execute_calls[-1]["tool_name"], "arch_draw_outer_outline")
        self.assertEqual(
            bridge.execute_calls[-1]["arguments"]["permission_request_id"],
            preview["permission_request_id"],
        )

    async def test_changed_geometry_rejects_old_ticket(self):
        executor, bridge = self.build_executor()
        original = {"boundary": [[0, 0], [10, 0], [10, 10], [0, 10]]}
        preview = await executor.execute_tool("arch_draw_outer_outline", original, dry_run=True)
        result = await executor.execute_tool(
            "arch_draw_outer_outline",
            {"boundary": [[0, 0], [20, 0], [20, 10], [0, 10]],
             "permission_token": preview["permission_token"], "preview_hash": preview["preview_hash"]},
            dry_run=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "permission_required")
        self.assertEqual(bridge.execute_calls, [])


if __name__ == "__main__":
    unittest.main()
