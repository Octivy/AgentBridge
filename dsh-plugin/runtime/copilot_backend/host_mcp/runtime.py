"""Host MCP executor: routes namespaced tools to discovered host adapters."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import types

from cadmcp.permission_ticket import PermissionTicketError, PermissionTicketService
from cadmcp.security_policy import evaluate_commit_policy
from host_runtime.client import HostClient, HostError
from host_runtime.registry import default_registry_dir, discover_hosts

from host_mcp.tooling import (
    HostTool,
    collect_host_tools,
    to_mcp_tool,
    tool_risk_level,
)


def _error_result(
    tool_name: str,
    error_code: str,
    error_message: str,
    *,
    trace_id: str = "",
    host_id: str = "",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool_name": tool_name,
        "summary": error_message,
        "data": None,
        "error_code": error_code,
        "error_message": error_message,
        "dry_run": None,
        "trace_id": trace_id,
        "host_id": host_id,
    }


def _normalize_result(
    tool_name: str,
    raw: Any,
    *,
    dry_run: bool,
    trace_id: str,
    host_id: str,
) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return _error_result(tool_name, "bad_result", "host returned a non-object result", trace_id=trace_id, host_id=host_id)
    result = dict(raw)
    data = result.get("result")
    normalized: Dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "tool_name": tool_name,
        "summary": str((data or {}).get("summary") or "") if isinstance(data, dict) else "",
        "data": data,
        "error_code": str(result.get("error_code") or ""),
        "error_message": str(result.get("error_message") or ""),
        "dry_run": bool(result.get("dry_run", dry_run)),
        "rollback_token": result.get("rollback_token"),
        "trace_id": trace_id,
        "host_id": host_id,
    }
    for key in (
        "requires_permission",
        "permission_token",
        "permission_request_id",
        "preview_hash",
        "permission_expires_at",
        "next_action",
    ):
        if key in result:
            normalized[key] = result[key]
    return normalized


class HostMcpExecutor:
    """Discover hosts, expose their tools through MCP, and enforce the
    dry-run -> one-time permission ticket -> commit policy."""

    def __init__(
        self,
        registry_dir: Optional[Path] = None,
        *,
        timeout_seconds: float = 10.0,
        permission_ttl_seconds: int = 600,
        refresh_ttl_seconds: float = 5.0,
    ) -> None:
        self._registry_dir = Path(registry_dir) if registry_dir else default_registry_dir()
        self._timeout_seconds = timeout_seconds
        self._permission_ttl_seconds = permission_ttl_seconds
        self._refresh_ttl_seconds = refresh_ttl_seconds
        self._tools: Dict[str, HostTool] = {}
        self._hosts: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._permission_services: Dict[str, PermissionTicketService] = {}
        self._cache_deadline = 0.0

    def refresh(self) -> None:
        tools, errors = collect_host_tools(self._registry_dir)
        self._tools = {tool.tool_name: tool for tool in tools}
        self._errors = errors
        hosts: Dict[str, Dict[str, Any]] = {}
        for registration in discover_hosts(self._registry_dir):
            health: Optional[Dict[str, Any]] = None
            status = "ok"
            try:
                health = HostClient(registration.endpoint, registration.token, self._timeout_seconds).health()
            except HostError as exc:
                status = f"error:{exc.error_code}"
            hosts[registration.host_id] = {
                "host_id": registration.host_id,
                "host_kind": registration.host_kind,
                "product": registration.product,
                "product_version": registration.product_version,
                "protocol_version": registration.protocol_version,
                "endpoint": registration.endpoint,
                "pid": registration.pid,
                "registered_at": registration.registered_at,
                "status": status,
                "health": health,
            }
        self._hosts = sorted(hosts.values(), key=lambda item: item["host_id"])
        self._cache_deadline = time.monotonic() + self._refresh_ttl_seconds

    def _refresh_if_stale(self) -> None:
        if time.monotonic() >= self._cache_deadline:
            self.refresh()

    def hosts(self) -> List[Dict[str, Any]]:
        self._refresh_if_stale()
        return list(self._hosts)

    def errors(self) -> List[Dict[str, Any]]:
        self._refresh_if_stale()
        return list(self._errors)

    def tool_names(self) -> List[str]:
        self._refresh_if_stale()
        return sorted(self._tools)

    def list_tools(self) -> List[types.Tool]:
        self._refresh_if_stale()
        return [to_mcp_tool(tool) for tool in self._tools.values()]

    def execute_tool_sync(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._refresh_if_stale()
        host_tool = self._tools.get(tool_name)
        if host_tool is None:
            return _error_result(tool_name, "unknown_tool", f"unknown host tool: {tool_name}")

        safe = dict(arguments or {})
        trace_id = str(safe.pop("trace_id", "") or "").strip()
        permission_token = str(safe.pop("permission_token", "") or "").strip()
        preview_hash = str(safe.pop("preview_hash", "") or "").strip()
        permission_request_id = str(safe.pop("permission_request_id", "") or "").strip()
        confirmed_by_local_user = bool(safe.pop("confirmed_by_local_user", False))
        task_id = str(safe.pop("task_id", "") or "").strip()
        requested_dry_run = safe.pop("dry_run", None)

        definition = host_tool.definition
        risk = tool_risk_level(definition)
        is_write = bool(definition.get("dry_run_supported")) and risk not in {"read_only", "preview_only"}
        dry_run = bool(requested_dry_run) if requested_dry_run is not None else is_write
        client = HostClient(host_tool.endpoint, host_tool.token, self._timeout_seconds)

        try:
            if is_write and not dry_run:
                policy = evaluate_commit_policy(
                    risk,
                    confirmed_by_local_user=confirmed_by_local_user,
                    task_id=task_id,
                )
                if not policy.allowed:
                    return _error_result(
                        tool_name,
                        policy.error_code,
                        policy.message,
                        trace_id=trace_id,
                        host_id=host_tool.host_id,
                    )
                ticket = self._consume_ticket(host_tool, safe, permission_token, preview_hash)
                if isinstance(ticket, dict) and ticket.get("ok") is False:
                    return ticket
                call_arguments = dict(safe)
                call_arguments["permission_request_id"] = permission_request_id or ticket["permission_request_id"]
                raw = client.execute_tool(
                    definition["tool_name"],
                    call_arguments,
                    dry_run=False,
                    trace_id=trace_id,
                )
            elif is_write and dry_run:
                raw = client.execute_tool(definition["tool_name"], safe, dry_run=True, trace_id=trace_id)
                if isinstance(raw, dict) and raw.get("ok"):
                    self._attach_grant(raw, host_tool, safe)
            else:
                raw = client.execute_tool(definition["tool_name"], safe, dry_run=False, trace_id=trace_id)
        except HostError as exc:
            return _error_result(
                tool_name,
                exc.error_code,
                str(exc),
                trace_id=trace_id,
                host_id=host_tool.host_id,
            )
        return _normalize_result(
            tool_name,
            raw,
            dry_run=dry_run,
            trace_id=trace_id,
            host_id=host_tool.host_id,
        )

    async def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await asyncio.to_thread(self.execute_tool_sync, tool_name, arguments)

    def _permission_service(self, host_tool: HostTool) -> PermissionTicketService:
        service = self._permission_services.get(host_tool.host_id)
        if service is None:
            service = PermissionTicketService(
                secret=host_tool.token,
                ttl_seconds=self._permission_ttl_seconds,
            )
            self._permission_services[host_tool.host_id] = service
        return service

    def _attach_grant(self, result: Dict[str, Any], host_tool: HostTool, arguments: Dict[str, Any]) -> None:
        grant = self._permission_service(host_tool).issue(host_tool.tool_name, arguments)
        result["requires_permission"] = True
        result["permission_request_id"] = grant.permission_request_id
        result["permission_token"] = grant.permission_token
        result["preview_hash"] = grant.preview_hash
        result["permission_expires_at"] = grant.expires_at
        result["next_action"] = {
            "type": "ask_permission",
            "label": "应用到软件",
            "permission_request_id": grant.permission_request_id,
        }

    def _consume_ticket(
        self,
        host_tool: HostTool,
        arguments: Dict[str, Any],
        permission_token: str,
        preview_hash: str,
    ) -> Dict[str, Any]:
        try:
            payload = self._permission_service(host_tool).consume(
                host_tool.tool_name,
                arguments,
                permission_token,
                expected_preview_hash=preview_hash,
            )
        except PermissionTicketError as exc:
            return _error_result(
                host_tool.tool_name,
                "permission_required",
                str(exc),
                host_id=host_tool.host_id,
            )
        return payload


__all__ = ["HostMcpExecutor"]
