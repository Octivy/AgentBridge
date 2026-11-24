import json
import os
import uuid
from typing import Any, Dict, Optional

import httpx

BRIDGE_PROTOCOL_VERSION = "2.0"

class CadBridgeError(RuntimeError):
    pass


class CadLocalBridgeClient:
    """HTTP adapter for the in-process AutoCAD bridge.

    Configuration is read at construction time so a standalone MCP host can
    provide environment variables without importing the backend settings
    module. Explicit values are useful for tests and embedded hosts.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.getenv("CADMCP_BRIDGE_URL")
            or os.getenv("CADCOPILOT_LOCAL_BRIDGE_URL")
            or "http://127.0.0.1:8765"
        ).rstrip("/")
        self._token = token if token is not None else (
            os.getenv("CADMCP_BRIDGE_TOKEN")
            or os.getenv("CADCOPILOT_LOCAL_BRIDGE_TOKEN")
            or ""
        )
        configured_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("CADMCP_BRIDGE_TIMEOUT_SECONDS")
            or os.getenv("CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS")
            or "30"
        )
        try:
            self._timeout = float(configured_timeout)
        except (TypeError, ValueError):
            self._timeout = 30.0

    async def health(self) -> Dict[str, Any]:
        data = await self._request("GET", "/health")
        result = data.get("result") if isinstance(data.get("result"), dict) else data.get("data")
        bridge = result.get("bridge") if isinstance(result, dict) else None
        protocol_version = str(bridge.get("protocol_version") or "") if isinstance(bridge, dict) else ""
        if protocol_version != BRIDGE_PROTOCOL_VERSION:
            raise CadBridgeError(
                "Local CAD bridge protocol mismatch: "
                f"expected {BRIDGE_PROTOCOL_VERSION}, received {protocol_version or 'missing'}."
            )
        return data

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        caller: str = "mcp_server",
        timeout_ms: int = 30000,
        dry_run: bool = False,
        trace_id: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "request_id": str(uuid.uuid4()),
            "trace_id": trace_id or "",
            "tool_name": tool_name,
            "arguments": arguments or {},
            "caller": caller,
            "timeout_ms": timeout_ms,
            "dry_run": dry_run,
        }
        return await self._request("POST", "/tools/execute", payload)

    async def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "x-cadmcp-protocol-version": BRIDGE_PROTOCOL_VERSION,
        }
        if self._token:
            headers["x-cadcopilot-token"] = self._token

        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                response = await client.request(method, f"{self._base_url}{path}", headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise CadBridgeError(f"Local CAD bridge timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise CadBridgeError(f"Local CAD bridge request failed: {exc}") from exc

        text = response.text.strip()
        try:
            data = response.json() if text else {}
        except json.JSONDecodeError as exc:
            raise CadBridgeError(f"Local CAD bridge returned invalid JSON: {text}") from exc

        if response.status_code >= 400:
            detail = data.get("error_message") or data.get("detail") or text or f"HTTP {response.status_code}"
            raise CadBridgeError(detail)

        return data
