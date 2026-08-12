import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_runtime.cad_bridge_client import CadLocalBridgeClient


class CadBridgeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_disables_environment_proxy_for_local_bridge(self) -> None:
        client = CadLocalBridgeClient()

        with patch("mcp_runtime.cad_bridge_client.httpx.AsyncClient") as async_client_factory:
            async_client = AsyncMock()
            response = Mock()
            response.text = '{"ok": true, "result": {"bridge": {"protocol_version": "2.0"}}}'
            response.status_code = 200
            response.json.return_value = {
                "ok": True,
                "result": {"bridge": {"protocol_version": "2.0"}},
            }
            async_client.request.return_value = response
            async_client_factory.return_value.__aenter__.return_value = async_client

            result = await client.health()

        self.assertTrue(result["ok"])
        self.assertEqual(async_client_factory.call_args.kwargs["trust_env"], False)
        request_headers = async_client.request.await_args.kwargs["headers"]
        self.assertEqual(request_headers["x-cadmcp-protocol-version"], "2.0")

    async def test_health_rejects_incompatible_bridge_protocol(self) -> None:
        client = CadLocalBridgeClient()

        with patch("mcp_runtime.cad_bridge_client.httpx.AsyncClient") as async_client_factory:
            async_client = AsyncMock()
            response = Mock()
            response.text = '{"ok": true, "result": {"bridge": {"protocol_version": "1.0"}}}'
            response.status_code = 200
            response.json.return_value = {
                "ok": True,
                "result": {"bridge": {"protocol_version": "1.0"}},
            }
            async_client.request.return_value = response
            async_client_factory.return_value.__aenter__.return_value = async_client

            with self.assertRaisesRegex(Exception, "protocol mismatch"):
                await client.health()


if __name__ == "__main__":
    unittest.main()
