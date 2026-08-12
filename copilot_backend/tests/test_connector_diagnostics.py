import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.cad_bridge_client import CadBridgeError
from connector_runtime.diagnostics import build_connector_capabilities, build_connector_diagnostics


class ConnectorDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def test_capabilities_publish_connector_contract(self):
        capabilities = build_connector_capabilities()
        self.assertEqual(capabilities["autocad_version"], "2024")
        self.assertEqual(capabilities["mcp"]["server"], "cadmcp")
        self.assertEqual(capabilities["mcp"]["tool_count"], 13)
        self.assertIn("anthropic_messages", capabilities["model_gateway"]["protocols"])
        self.assertTrue(capabilities["model_gateway"]["supports_local_openai_compatible"])
        self.assertTrue(capabilities["skills"]["task_to_draft"])
        self.assertFalse(capabilities["skills"]["automatic_enable"])

    async def test_diagnostics_reports_all_five_layers(self):
        health = {
            "ok": True,
            "result": {
                "bridge": {"protocol_version": "2.0", "auth_required": False},
                "autocad": {"document_open": True, "document_name": "sample.dwg"},
                "plugin": {"version": "0.9.0.622"},
            },
        }
        with patch(
            "connector_runtime.diagnostics.CadLocalBridgeClient.health",
            AsyncMock(return_value=health),
        ):
            diagnostics = await build_connector_diagnostics()
        self.assertEqual(diagnostics["status"], "ok")
        self.assertEqual(
            {item["id"] for item in diagnostics["components"]},
            {"backend", "mcp", "model_gateway", "local_bridge", "autocad"},
        )

    async def test_diagnostics_classifies_unreachable_bridge(self):
        with patch(
            "connector_runtime.diagnostics.CadLocalBridgeClient.health",
            AsyncMock(side_effect=CadBridgeError("local CAD bridge is unreachable")),
        ):
            diagnostics = await build_connector_diagnostics()
        bridge = next(item for item in diagnostics["components"] if item["id"] == "local_bridge")
        self.assertEqual(diagnostics["status"], "failed")
        self.assertEqual(bridge["details"]["error_code"], "bridge_unreachable")


if __name__ == "__main__":
    unittest.main()
