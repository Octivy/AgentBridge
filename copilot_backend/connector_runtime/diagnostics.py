from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from cadmcp.cad_bridge_client import BRIDGE_PROTOCOL_VERSION, CadBridgeError, CadLocalBridgeClient
from cadmcp.tool_registry import list_product_tools
from product.model_config_service import get_runtime_model_provider_config
from shared.config_contract import validate_product_config
from shared import settings
from skills.registry import list_skills


SUPPORTED_PROVIDER_PROTOCOLS = ("openai_chat", "openai_responses", "anthropic_messages")
SUPPORTED_MCP_TRANSPORTS = ("stdio", "streamable-http")


def build_connector_capabilities() -> dict[str, Any]:
    runtime_provider = get_runtime_model_provider_config()
    return {
        "schema_version": "1.0",
        "connector": "cadcopilot",
        "autocad_version": "2024",
        "mcp": {
            "server": "cadmcp",
            "transports": list(SUPPORTED_MCP_TRANSPORTS),
            "tool_count": len(list_product_tools()),
        },
        "model_gateway": {
            "protocols": list(SUPPORTED_PROVIDER_PROTOCOLS),
            "configured_provider": runtime_provider.provider if runtime_provider else None,
            "configured_protocol": runtime_provider.protocol if runtime_provider else None,
            "supports_request_scoped_provider": True,
            "supports_local_openai_compatible": True,
        },
        "agents": {
            "external_mcp_hosts": True,
            "builtin_planner": True,
            "task_resume_retry_cancel": True,
            "write_requires_local_confirmation": True,
        },
        "skills": {
            "builtin_count": len(list_skills(enabled_only=True)),
            "draft_creation": True,
            "task_to_draft": True,
            "draft_edit_validate_approve": True,
            "automatic_enable": False,
        },
        "knowledge": {
            "local_approved_roots": True,
            "configured": bool(settings.CADCOPILOT_KNOWLEDGE_ROOTS),
            "grounded_citations": True,
            "refuses_unsourced_answers": True,
        },
    }


async def build_connector_diagnostics() -> dict[str, Any]:
    trace_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()
    capabilities = build_connector_capabilities()
    components: list[dict[str, Any]] = []

    components.append(
        _component(
            "backend",
            "Backend HTTP",
            "ok",
            "Backend API is running.",
            {"health_endpoint": "/health", "diagnostics_endpoint": "/connector/diagnostics"},
        )
    )

    tools = list_product_tools()
    skills = list_skills(enabled_only=True)
    components.append(
        _component(
            "mcp",
            "CADMCP",
            "ok" if len(tools) == 13 else "warning",
            f"{len(tools)} tools and {len(skills)} enabled skills are registered.",
            {
                "server": "cadmcp",
                "transports": list(SUPPORTED_MCP_TRANSPORTS),
                "tool_count": len(tools),
                "skill_count": len(skills),
            },
        )
    )

    runtime_provider = get_runtime_model_provider_config()
    config_validation = validate_product_config()
    provider_status = "ok" if runtime_provider else "ready"
    provider_summary = (
        f"{runtime_provider.display_name} / {runtime_provider.model} / {runtime_provider.protocol}"
        if runtime_provider
        else "No central provider selected; request-scoped or plugin-local provider configuration is available."
    )
    components.append(
        _component(
            "model_gateway",
            "Model gateway",
            provider_status,
            provider_summary,
            {
                "provider": runtime_provider.provider if runtime_provider else None,
                "model": runtime_provider.model if runtime_provider else None,
                "protocol": runtime_provider.protocol if runtime_provider else None,
                "capabilities": list(runtime_provider.capabilities) if runtime_provider else [],
                "config_valid": config_validation.ok,
                "supported_protocols": list(SUPPORTED_PROVIDER_PROTOCOLS),
                "knowledge_roots_configured": bool(settings.CADCOPILOT_KNOWLEDGE_ROOTS),
            },
        )
    )

    try:
        bridge_health = await CadLocalBridgeClient(timeout_seconds=3).health()
        result = bridge_health.get("result") if isinstance(bridge_health, dict) else None
        result = result if isinstance(result, dict) else {}
        bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
        autocad = result.get("autocad") if isinstance(result.get("autocad"), dict) else {}
        plugin = result.get("plugin") if isinstance(result.get("plugin"), dict) else {}
        components.append(
            _component(
                "local_bridge",
                "AutoCAD local bridge",
                "ok",
                "Local bridge is reachable and the protocol matches.",
                {
                    "protocol_version": bridge.get("protocol_version"),
                    "expected_protocol_version": BRIDGE_PROTOCOL_VERSION,
                    "auth_required": bool(bridge.get("auth_required")),
                    "plugin_version": plugin.get("version"),
                },
            )
        )
        document_open = bool(autocad.get("document_open"))
        components.append(
            _component(
                "autocad",
                "AutoCAD 2024",
                "ok" if document_open else "warning",
                "An active drawing is open." if document_open else "Plugin is reachable, but no active drawing is open.",
                {
                    "document_open": document_open,
                    "document_name": autocad.get("document_name") or "",
                },
            )
        )
    except CadBridgeError as exc:
        error_code = _bridge_error_code(str(exc))
        components.append(
            _component(
                "local_bridge",
                "AutoCAD local bridge",
                "failed",
                str(exc),
                {
                    "error_code": error_code,
                    "expected_protocol_version": BRIDGE_PROTOCOL_VERSION,
                },
                action=_bridge_recovery_action(error_code),
            )
        )
        components.append(
            _component(
                "autocad",
                "AutoCAD 2024",
                "unknown",
                "AutoCAD state cannot be checked until the local bridge is available.",
                {"document_open": None},
                action="Load the AutoCAD 2024 plugin, then retry connector diagnostics.",
            )
        )

    statuses = {item["status"] for item in components}
    overall = "failed" if "failed" in statuses else "degraded" if "warning" in statuses else "ok"
    return {
        "schema_version": "1.0",
        "trace_id": trace_id,
        "generated_at": generated_at,
        "status": overall,
        "components": components,
        "capabilities": capabilities,
    }


def _component(
    component_id: str,
    name: str,
    status: str,
    summary: str,
    details: dict[str, Any],
    *,
    action: str = "",
) -> dict[str, Any]:
    return {
        "id": component_id,
        "name": name,
        "status": status,
        "summary": summary,
        "details": details,
        "action": action,
    }


def _bridge_error_code(message: str) -> str:
    value = (message or "").lower()
    if "protocol mismatch" in value:
        return "bridge_protocol_mismatch"
    if "unauthorized" in value or "token" in value:
        return "bridge_unauthorized"
    if "timed out" in value:
        return "bridge_timeout"
    return "bridge_unreachable"


def _bridge_recovery_action(error_code: str) -> str:
    if error_code == "bridge_protocol_mismatch":
        return "Rebuild and reload the AutoCAD plugin and restart cadmcp/backend so protocol versions match."
    if error_code == "bridge_unauthorized":
        return "Make CADMCP_BRIDGE_TOKEN and the plugin local bridge token identical."
    if error_code == "bridge_timeout":
        return "Confirm AutoCAD is responsive and retry; then inspect the plugin log for a blocked main thread."
    return "Start AutoCAD 2024, load AgentBridge, and verify the local bridge URL and port."
