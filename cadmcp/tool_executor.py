from typing import Any, Dict, Optional

from cadmcp.cad_bridge_client import CadBridgeError, CadLocalBridgeClient
from cadmcp.permission_ticket import PermissionTicketError, PermissionTicketService, permission_ticket_service
from cadmcp.result_protocol import build_tool_error_result, normalize_tool_result
from cadmcp.security_policy import evaluate_commit_policy
from cadmcp.tool_registry import get_tool
from cadmcp.tools.architecture import execute_architecture_tool


class CadToolExecutor:
    _VERIFIED_CAD_WRITES = {
        "draw_line",
        "execute_draw_batch",
        "cad_rollback_transaction",
    }
    _STABLE_OBJECT_ID_TOOLS = {
        "arch_draw_outer_outline": "outer-outline",
    }
    _VERIFIED_ARCHITECTURE_WRITES = {
        "arch_draw_outer_outline",
        "arch_apply_layer_mapping",
    }

    def __init__(
        self,
        cad_bridge_client: Optional[CadLocalBridgeClient] = None,
        permission_service: Optional[PermissionTicketService] = None,
    ) -> None:
        self._cad_bridge_client = cad_bridge_client or CadLocalBridgeClient()
        self._permission_service = permission_service or permission_ticket_service

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        caller: str = "planner_runtime",
        timeout_ms: int = 30000,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        safe_arguments = dict(arguments or {})
        trace_id = str(safe_arguments.pop("trace_id", "") or "").strip()
        permission_token = str(safe_arguments.pop("permission_token", "") or "").strip()
        preview_hash = str(safe_arguments.pop("preview_hash", "") or "").strip()
        permission_request_id = str(safe_arguments.pop("permission_request_id", "") or "").strip()
        task_id = str(safe_arguments.pop("task_id", "") or "").strip()
        confirmed_by_local_user = bool(safe_arguments.pop("confirmed_by_local_user", False))
        tool = get_tool(tool_name)
        is_write = bool(
            tool is not None
            and tool.dry_run_supported
            and tool.risk_level not in {"read_only", "preview_only"}
        )
        self._ensure_stable_object_id(tool_name, safe_arguments)

        try:
            if is_write and not dry_run:
                policy = evaluate_commit_policy(
                    tool.risk_level,
                    confirmed_by_local_user=confirmed_by_local_user,
                    task_id=task_id,
                )
                if not policy.allowed:
                    return self._with_trace(
                        normalize_tool_result(
                            tool_name,
                            build_tool_error_result(tool_name, policy.error_code, policy.message),
                        ),
                        trace_id,
                    )

            if tool_name in {
                "arch_get_drawing_context",
                "arch_recognize_functional_objects",
                "arch_extract_outer_outline",
                "arch_suggest_layer_mapping",
            } and not isinstance(safe_arguments.get("snapshot"), dict):
                snapshot_error = await self._inject_drawing_snapshot(
                    tool_name,
                    safe_arguments,
                    caller=caller,
                    timeout_ms=timeout_ms,
                    trace_id=trace_id,
                )
                if snapshot_error is not None:
                    return snapshot_error

            if tool_name.startswith("arch_") and is_write:
                if dry_run:
                    result = normalize_tool_result(
                        tool_name,
                        await execute_architecture_tool(tool_name, safe_arguments, dry_run=True),
                    )
                    if result.get("ok"):
                        self._attach_permission_grant(result, tool_name, safe_arguments, trace_id, task_id)
                    return self._with_trace(result, trace_id)

                ticket_or_error = self._consume_ticket(
                    tool_name,
                    safe_arguments,
                    permission_token,
                    preview_hash,
                    trace_id,
                )
                if isinstance(ticket_or_error, dict) and ticket_or_error.get("ok") is False:
                    return ticket_or_error
                return await self._commit_to_bridge(
                    tool_name,
                    safe_arguments,
                    ticket_or_error,
                    permission_request_id=permission_request_id,
                    caller=caller,
                    timeout_ms=timeout_ms,
                    trace_id=trace_id,
                    task_id=task_id,
                    confirmed_by_local_user=confirmed_by_local_user,
                    require_verification=tool_name in self._VERIFIED_ARCHITECTURE_WRITES,
                )

            if tool_name.startswith("arch_"):
                result = normalize_tool_result(
                    tool_name,
                    await execute_architecture_tool(tool_name, safe_arguments, dry_run=dry_run),
                )
                return self._with_trace(result, trace_id)

            if tool_name == "cad_health_check":
                return self._with_trace(
                    normalize_tool_result(tool_name, await self._cad_bridge_client.health()),
                    trace_id,
                )

            if is_write and not dry_run:
                ticket_or_error = self._consume_ticket(
                    tool_name,
                    safe_arguments,
                    permission_token,
                    preview_hash,
                    trace_id,
                )
                if isinstance(ticket_or_error, dict) and ticket_or_error.get("ok") is False:
                    return ticket_or_error
                return await self._commit_to_bridge(
                    tool_name,
                    safe_arguments,
                    ticket_or_error,
                    permission_request_id=permission_request_id,
                    caller=caller,
                    timeout_ms=timeout_ms,
                    trace_id=trace_id,
                    task_id=task_id,
                    confirmed_by_local_user=confirmed_by_local_user,
                    require_verification=tool_name in self._VERIFIED_CAD_WRITES,
                )

            result = normalize_tool_result(
                tool_name,
                await self._cad_bridge_client.execute_tool(
                    tool_name,
                    safe_arguments,
                    caller=caller,
                    timeout_ms=timeout_ms,
                    dry_run=dry_run,
                    trace_id=trace_id,
                ),
            )
            if is_write and dry_run and result.get("ok"):
                self._attach_permission_grant(result, tool_name, safe_arguments, trace_id, task_id)
            return self._with_trace(result, trace_id)
        except CadBridgeError as exc:
            if dry_run:
                preview_result = self._build_remote_dry_run_preview(tool_name, safe_arguments, trace_id)
                if preview_result is not None:
                    normalized = normalize_tool_result(tool_name, preview_result)
                    if is_write and normalized.get("ok"):
                        self._attach_permission_grant(normalized, tool_name, safe_arguments, trace_id, task_id)
                    return self._with_trace(normalized, trace_id)

            return self._with_trace(build_tool_error_result(tool_name, "cad_bridge_error", str(exc)), trace_id)

    async def _inject_drawing_snapshot(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        caller: str,
        timeout_ms: int,
        trace_id: str,
    ) -> Optional[Dict[str, Any]]:
        snapshot_result = normalize_tool_result(
            "get_drawing_snapshot",
            await self._cad_bridge_client.execute_tool(
                "get_drawing_snapshot",
                {},
                caller=caller,
                timeout_ms=timeout_ms,
                dry_run=False,
                trace_id=trace_id,
            ),
        )
        if not snapshot_result.get("ok"):
            return self._with_trace(
                build_tool_error_result(
                    tool_name,
                    str(snapshot_result.get("error_code") or "snapshot_error"),
                    str(
                        snapshot_result.get("error_message")
                        or snapshot_result.get("summary")
                        or "Failed to read drawing snapshot."
                    ),
                ),
                trace_id,
            )
        snapshot_data = snapshot_result.get("data") if isinstance(snapshot_result.get("data"), dict) else {}
        arguments["snapshot"] = (
            snapshot_data.get("snapshot")
            if isinstance(snapshot_data.get("snapshot"), dict)
            else snapshot_data
        )
        return None

    async def _commit_to_bridge(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        ticket: Dict[str, Any],
        *,
        permission_request_id: str,
        caller: str,
        timeout_ms: int,
        trace_id: str,
        task_id: str,
        confirmed_by_local_user: bool,
        require_verification: bool,
    ) -> Dict[str, Any]:
        bridge_arguments = dict(arguments)
        if task_id:
            bridge_arguments["task_id"] = task_id
        if confirmed_by_local_user:
            bridge_arguments["confirmed_by_local_user"] = True
        bridge_arguments["permission_request_id"] = str(
            ticket.get("permission_request_id") or permission_request_id
        )
        result = normalize_tool_result(
            tool_name,
            await self._cad_bridge_client.execute_tool(
                tool_name,
                bridge_arguments,
                caller=caller,
                timeout_ms=timeout_ms,
                dry_run=False,
                trace_id=trace_id,
            ),
        )
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if result.get("ok") and require_verification and not bool(data.get("verified")):
            result = normalize_tool_result(
                tool_name,
                build_tool_error_result(
                    tool_name,
                    "verification_failed",
                    "CAD bridge did not verify the committed entities.",
                ),
            )
        result["permission_request_id"] = str(ticket.get("permission_request_id") or "") or None
        result["preview_hash"] = str(ticket.get("preview_hash") or "") or None
        result["permission_token"] = None
        result["permission_expires_at"] = None
        result["requires_permission"] = False
        result["audit"] = {
            "phase": "commit",
            "preview_hash": str(ticket.get("preview_hash") or ""),
            "permission_request_id": str(ticket.get("permission_request_id") or ""),
            "confirmed_by_local_user": confirmed_by_local_user,
            "trace_id": trace_id,
            "task_id": task_id,
            "verified": bool(data.get("verified")) if require_verification else bool(result.get("ok")),
        }
        return self._with_trace(result, trace_id)

    def _consume_ticket(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_token: str,
        preview_hash: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        try:
            return self._permission_service.consume(
                tool_name,
                arguments,
                permission_token,
                expected_preview_hash=preview_hash,
            )
        except PermissionTicketError as exc:
            result = normalize_tool_result(
                tool_name,
                build_tool_error_result(tool_name, "permission_required", str(exc)),
            )
            result["requires_permission"] = True
            result["next_action"] = {"type": "regenerate_preview", "label": "重新生成预览"}
            return self._with_trace(result, trace_id)

    def _attach_permission_grant(
        self,
        result: Dict[str, Any],
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str,
        task_id: str,
    ) -> None:
        grant = self._permission_service.issue(tool_name, arguments)
        result["requires_permission"] = True
        result["permission_request_id"] = grant.permission_request_id
        result["permission_token"] = grant.permission_token
        result["preview_hash"] = grant.preview_hash
        result["permission_expires_at"] = grant.expires_at
        result["next_action"] = {
            "type": "ask_permission",
            "label": "应用到图纸",
            "permission_request_id": grant.permission_request_id,
        }
        result["audit"] = {
            "phase": "preview",
            "preview_hash": grant.preview_hash,
            "trace_id": trace_id,
            "task_id": task_id,
        }

    def _ensure_stable_object_id(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        prefix = self._STABLE_OBJECT_ID_TOOLS.get(tool_name)
        if prefix and not str(arguments.get("object_id") or "").strip():
            arguments["object_id"] = (
                prefix + "-" + self._permission_service.preview_hash(tool_name, arguments)[:24]
            )

    @staticmethod
    def _with_trace(result: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        if trace_id:
            result["trace_id"] = trace_id
        return result

    @staticmethod
    def _build_remote_dry_run_preview(
        tool_name: str,
        arguments: Dict[str, Any],
        trace_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        tool = get_tool(tool_name)
        if tool is None or not tool.dry_run_supported:
            return None

        data: Dict[str, Any] = {
            "dry_run": True,
            "local_execution_required": True,
            "preview_source": "nas_without_local_bridge",
        }
        if tool_name == "execute_draw_batch":
            commands = arguments.get("commands")
            if not isinstance(commands, list) or not commands:
                return build_tool_error_result(tool_name, "invalid_arguments", "commands array is required.")
            data["commands"] = commands
            data["command_count"] = len(commands)
        elif tool_name == "ensure_layer":
            layer = str(arguments.get("layer") or arguments.get("layer_name") or "").strip()
            if not layer:
                return build_tool_error_result(tool_name, "invalid_arguments", "layer is required.")
            data["layer"] = layer
            if "color" in arguments:
                data["color"] = arguments.get("color")
        else:
            data.update(arguments)

        result = {
            "ok": True,
            "tool_name": tool_name,
            "summary": "已生成更改预览，等待确认后应用到图纸。",
            "dry_run": True,
            "affected_entities_count": 0,
            "data": data,
        }
        if trace_id:
            result["trace_id"] = trace_id
        return result


cad_tool_executor = CadToolExecutor()
