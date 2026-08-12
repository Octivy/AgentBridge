"""ControlService: business logic behind the control-plane MCP tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import types

from control_mcp.scaffold import scaffold_adapter
from control_mcp.tools import control_tools
from agent.host_task import AgentTaskRequest, run_host_task
from delivery.models import DeliverableCreate, HandoffUpdate
from delivery.service import DeliveryService
from host_config.models import HostConfigCreate, HostConfigUpdate, LaunchSpec
from host_config.service import HostConfigService, host_config_service
from mcp_registry.service import (
    build_claude_json,
    build_mcp_servers,
    render_codex_toml,
    write_claude_config,
    write_codex_config,
)


def _error(tool_name: str, message: str, code: str = "error") -> Dict[str, Any]:
    return {"ok": False, "tool_name": tool_name, "error_code": code, "error_message": message}


def _ok(tool_name: str, result: Any) -> Dict[str, Any]:
    return {"ok": True, "tool_name": tool_name, "result": result}


class ControlService:
    """Expose the configuration center as tools an agent can drive."""

    def __init__(
        self,
        host_service: Optional[HostConfigService] = None,
        host_config_store=None,
        registry_dir: Optional[Path] = None,
        delivery: Optional[DeliveryService] = None,
        task_runner=None,
    ) -> None:
        if host_service is None:
            host_service = HostConfigService(store=host_config_store, registry_dir=registry_dir)
        self._host_service = host_service
        self._delivery = delivery or DeliveryService()
        self._task_runner = task_runner or run_host_task
        self._tools = {tool.name: tool for tool in control_tools()}

    def list_tools(self) -> List[types.Tool]:
        return list(self._tools.values())

    def execute_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        handler = getattr(self, f"_run_{name}", None)
        if handler is None:
            return _error(name, f"unknown control tool: {name}", "unknown_tool")
        try:
            return handler(dict(arguments or {}))
        except KeyError as exc:
            return _error(name, str(exc), "not_found")
        except ValueError as exc:
            return _error(name, str(exc), "invalid_arguments")
        except Exception as exc:  # noqa: BLE001
            return _error(name, f"{type(exc).__name__}: {exc}", "internal_error")

    async def execute_async(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if name == "ab_run_task":
            return await self._run_ab_run_task(dict(arguments or {}))
        return await asyncio.to_thread(self.execute_tool, name, arguments)

    # ----- software bridges -----

    def _run_ab_list_software(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _ok("ab_list_software", [status.model_dump() for status in self._host_service.list_status()])

    def _run_ab_software_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        return _ok("ab_software_status", self._host_service.status(host_id).model_dump())

    def _run_ab_test_connection(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        return _ok("ab_test_connection", self._host_service.test(host_id).model_dump())

    def _run_ab_start_host(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        return _ok("ab_start_host", self._host_service.start(host_id).model_dump())

    def _run_ab_stop_host(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        return _ok("ab_stop_host", self._host_service.stop(host_id).model_dump())

    def _run_ab_add_host(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        request = HostConfigCreate(
            host_id=str(arguments["host_id"]).strip(),
            name=str(arguments["name"]).strip(),
            host_kind=str(arguments["host_kind"]).strip(),
            product=str(arguments.get("product") or "").strip(),
            auto_start=bool(arguments.get("auto_start", False)),
            launch=LaunchSpec(
                command=str(arguments.get("command") or "").strip(),
                args=[str(item) for item in (arguments.get("args") or [])],
                cwd=str(arguments.get("cwd") or "").strip(),
                env_vars=[str(item) for item in (arguments.get("env_vars") or [])],
            ),
        )
        return _ok("ab_add_host", self._host_service.create_config(request).model_dump())

    def _run_ab_update_host(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        launch_fields: Dict[str, Any] = {}
        for field in ("command", "args", "cwd", "env_vars"):
            if field in arguments:
                launch_fields[field] = arguments[field]
        update = HostConfigUpdate(
            **{field: arguments[field] for field in ("name", "host_kind", "product", "enabled", "auto_start", "notes") if field in arguments}
        )
        if launch_fields:
            existing = self._host_service.get_config(host_id)
            if existing is None:
                raise KeyError(f"host config not found: {host_id}")
            merged = existing.launch.model_copy(update={k: v for k, v in launch_fields.items() if v is not None})
            update = update.model_copy(update={"launch": merged})
        return _ok("ab_update_host", self._host_service.update_config(host_id, update).model_dump())

    def _run_ab_remove_host(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host_id = str(arguments["host_id"]).strip()
        removed = self._host_service.delete_config(host_id)
        if not removed:
            raise KeyError(f"host config not found: {host_id}")
        return _ok("ab_remove_host", {"removed": True, "host_id": host_id})

    # ----- MCP registration -----

    def _run_ab_preview_mcp(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        entries = build_mcp_servers()
        return _ok(
            "ab_preview_mcp",
            {
                "servers": [entry.model_dump() for entry in entries],
                "codex_toml": render_codex_toml(entries),
                "claude_json": build_claude_json(entries),
            },
        )

    def _run_ab_register_with_codex(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = write_codex_config(build_mcp_servers())
        return _ok("ab_register_with_codex", result)

    def _run_ab_register_with_claude(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = write_claude_config(build_mcp_servers())
        return _ok("ab_register_with_claude", result)

    # ----- adapter scaffolding -----

    def _run_ab_scaffold_adapter(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = Path(str(arguments["target_dir"]).strip()) if arguments.get("target_dir") else None
        result = scaffold_adapter(
            host_kind=str(arguments["host_kind"]),
            product=str(arguments["product"]),
            target_dir=target,
        )
        return _ok("ab_scaffold_adapter", result)

    # ----- task delivery -----

    def _run_ab_list_deliveries(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return _ok("ab_list_deliveries", [view.model_dump() for view in self._delivery.list()])

    def _run_ab_record_deliverable(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        view = self._delivery.add_deliverable(
            str(arguments["task_id"]).strip(),
            DeliverableCreate(
                name=str(arguments["name"]).strip(),
                kind=str(arguments.get("kind") or "file").strip(),
                path=str(arguments["path"]).strip(),
                description=str(arguments.get("description") or "").strip(),
            ),
        )
        return _ok("ab_record_deliverable", view.model_dump())

    def _run_ab_set_handoff(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        view = self._delivery.set_handoff(
            str(arguments["task_id"]).strip(),
            HandoffUpdate(
                summary=str(arguments.get("summary") or "").strip(),
                verification_steps=[str(item) for item in (arguments.get("verification_steps") or [])],
                next_steps=[str(item) for item in (arguments.get("next_steps") or [])],
            ),
        )
        return _ok("ab_set_handoff", view.model_dump())

    async def _run_ab_run_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            request = AgentTaskRequest(
                message=str(arguments.get("message") or "").strip(),
                provider=str(arguments.get("provider") or "").strip() or None,
                model=str(arguments.get("model") or "").strip() or None,
                api_key=str(arguments.get("api_key") or "").strip() or None,
                api_base_url=str(arguments.get("api_base_url") or "").strip() or None,
                protocol=str(arguments.get("protocol") or "").strip() or None,
                approval=str(arguments.get("approval") or "full").strip(),
                max_iterations=int(arguments.get("max_iterations") or 12),
                tool_scope=str(arguments.get("tool_scope") or "hosts").strip(),
            )
            if not request.message:
                raise ValueError("message is required")
            result = await self._task_runner(request)
            return _ok("ab_run_task", result)
        except Exception as exc:  # noqa: BLE001
            return _error("ab_run_task", f"{type(exc).__name__}: {exc}", "task_failed")


default_control_service = ControlService(host_service=host_config_service)


__all__ = ["ControlService", "default_control_service"]
