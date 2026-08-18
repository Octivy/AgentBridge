"""HTTP client for talking to host adapters (Host Adapter Contract v1)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class HostError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "host_error", status_code: int = 0) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class HostClient:
    """Small client for a single host adapter endpoint."""

    def __init__(self, endpoint: str, token: str, timeout_seconds: float = 10.0) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._headers = {
            "x-cadcopilot-token": token,
            "Content-Type": "application/json",
        }
        self._timeout = timeout_seconds

    def manifest(self) -> Dict[str, Any]:
        return self._request("GET", "/manifest")

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def snapshot(self, scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("POST", "/snapshot", {"scope": scope or {}})

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        dry_run: bool = False,
        trace_id: str = "",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/tools/{tool_name}",
            {
                "arguments": arguments or {},
                "dry_run": bool(dry_run),
                "trace_id": trace_id or "",
            },
        )

    def rollback(self, rollback_token: str) -> Dict[str, Any]:
        return self._request("POST", "/rollback", {"rollback_token": rollback_token})

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            response = httpx.request(
                method,
                self._endpoint + path,
                headers=self._headers,
                json=payload,
                timeout=self._timeout,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            raise HostError(f"host request failed: {exc}", error_code="connection_error") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise HostError(
                f"host returned non-JSON response ({response.status_code})",
                error_code="bad_response",
                status_code=response.status_code,
            ) from exc
        if response.status_code >= 400 or data.get("ok") is False:
            raise HostError(
                str(data.get("error_message") or data.get("message") or "host error"),
                error_code=str(data.get("error_code") or "host_error"),
                status_code=response.status_code,
            )
        return data


__all__ = ["HostClient", "HostError"]
