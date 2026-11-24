from typing import Any, Dict, Optional


STANDARD_TOOL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "tool_name": {"type": "string"},
        "summary": {"type": "string"},
        "data": {"type": ["object", "array", "string", "number", "boolean", "null"]},
        "error_code": {"type": ["string", "null"]},
        "error_message": {"type": ["string", "null"]},
        "dry_run": {"type": ["boolean", "null"]},
        "request_id": {"type": ["string", "null"]},
        "trace_id": {"type": ["string", "null"]},
        "affected_entities_count": {"type": ["integer", "null"]},
        "assistant_message": {"type": "string"},
        "risk_level": {"type": "string"},
        "requires_permission": {"type": "boolean"},
        "permission_request_id": {"type": ["string", "null"]},
        "permission_token": {"type": ["string", "null"]},
        "preview_hash": {"type": ["string", "null"]},
        "permission_expires_at": {"type": ["integer", "null"]},
        "affected_entities": {"type": "array"},
        "cad_operations": {"type": "array"},
        "preview": {"type": "object"},
        "transaction": {"type": "object"},
        "next_action": {"type": "object"},
        "audit": {"type": "object"},
    },
    "required": [
        "ok",
        "tool_name",
        "summary",
        "data",
        "error_code",
        "error_message",
        "dry_run",
        "request_id",
        "affected_entities_count",
    ],
    "additionalProperties": False,
}

_METADATA_KEYS = {
    "ok",
    "tool_name",
    "summary",
    "data",
    "error_code",
    "error_message",
    "dry_run",
    "message",
    "detail",
    "result",
    "execution_log",
    "request_id",
    "trace_id",
    "affected_entities_count",
    "assistant_message",
    "risk_level",
    "requires_permission",
    "permission_request_id",
    "permission_token",
    "preview_hash",
    "permission_expires_at",
    "affected_entities",
    "cad_operations",
    "preview",
    "transaction",
    "next_action",
    "audit",
}


def normalize_tool_result(tool_name: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    ok = bool(source.get("ok", True))
    data = _extract_data(source)
    summary = _build_summary(tool_name=tool_name, payload=source, data=data, ok=ok)
    dry_run = _extract_dry_run(source, data)
    request_id = _first_text(source.get("request_id"))
    affected_entities_count = _extract_affected_entities_count(source, data)

    error_code = _first_text(source.get("error_code")) if not ok else None
    error_message = _first_text(source.get("error_message"), source.get("detail"), summary if not ok else None)

    normalized = {
        "ok": ok,
        "tool_name": _first_text(source.get("tool_name"), tool_name) or tool_name,
        "summary": summary,
        "data": data,
        "error_code": error_code,
        "error_message": error_message,
        "dry_run": dry_run,
        "request_id": request_id,
        "affected_entities_count": affected_entities_count,
    }
    return _attach_harness_fields(normalized["tool_name"], normalized, source, data)


def build_tool_error_result(tool_name: str, error_code: str, error_message: str) -> Dict[str, Any]:
    message = (error_message or "工具执行失败。").strip()
    return {
        "ok": False,
        "tool_name": tool_name,
        "summary": message,
        "data": None,
        "error_code": (error_code or "tool_error").strip() or "tool_error",
        "error_message": message,
        "dry_run": None,
        "request_id": None,
        "affected_entities_count": None,
    }


def _extract_data(source: Dict[str, Any]) -> Any:
    if "data" in source:
        return source.get("data")
    if "result" in source:
        return source.get("result")

    extra = {key: value for key, value in source.items() if key not in _METADATA_KEYS}
    if extra:
        return extra
    return None


def _extract_dry_run(source: Dict[str, Any], data: Any) -> Optional[bool]:
    if isinstance(source.get("dry_run"), bool):
        return source.get("dry_run")
    if isinstance(data, dict) and isinstance(data.get("dry_run"), bool):
        return data.get("dry_run")
    return None


def _extract_affected_entities_count(source: Dict[str, Any], data: Any) -> Optional[int]:
    value = source.get("affected_entities_count")
    if isinstance(value, int):
        return value
    if isinstance(data, dict) and isinstance(data.get("affected_entities_count"), int):
        return data.get("affected_entities_count")
    return None


def _attach_harness_fields(tool_name: str, result: Dict[str, Any], source: Dict[str, Any], data: Any) -> Dict[str, Any]:
    tool = _get_tool_metadata(tool_name)
    risk_level = _first_text(source.get("risk_level"), getattr(tool, "risk_level", None), "critical") or "critical"
    dry_run = result.get("dry_run")
    requires_permission = source.get("requires_permission")
    if not isinstance(requires_permission, bool):
        requires_permission = bool(
            dry_run is True
            and risk_level in {"reversible_write", "destructive_write", "external_side_effect", "critical"}
        )

    result["assistant_message"] = _first_text(source.get("assistant_message"), result.get("summary")) or ""
    result["risk_level"] = risk_level
    result["requires_permission"] = requires_permission
    result["permission_request_id"] = _first_text(source.get("permission_request_id"))
    result["permission_token"] = _first_text(source.get("permission_token"))
    result["preview_hash"] = _first_text(source.get("preview_hash"))
    result["permission_expires_at"] = _extract_optional_int(source, data, "permission_expires_at")
    result["affected_entities"] = _extract_list(source, data, "affected_entities")
    result["cad_operations"] = _extract_list(source, data, "cad_operations")
    result["preview"] = _extract_dict(source, data, "preview") or {
        "kind": _first_text(getattr(tool, "ui_preview_kind", None), "none") or "none",
        "items": [],
    }
    result["transaction"] = _extract_dict(source, data, "transaction") or {
        "transaction_id": None,
        "rollback_token": None,
        "undo_group": None,
    }
    result["next_action"] = _extract_dict(source, data, "next_action") or (
        {"type": "ask_permission", "label": "应用到图纸"} if requires_permission else {"type": "none"}
    )
    result["audit"] = _extract_dict(source, data, "audit") or {}
    return result


def _get_tool_metadata(tool_name: str) -> Any:
    try:
        from cadmcp.tool_registry import get_tool

        return get_tool(tool_name)
    except Exception:
        return None


def _extract_list(source: Dict[str, Any], data: Any, key: str) -> list:
    value = source.get(key)
    if isinstance(value, list):
        return value
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data.get(key) or []
    return []


def _extract_dict(source: Dict[str, Any], data: Any, key: str) -> Dict[str, Any]:
    value = source.get(key)
    if isinstance(value, dict):
        return dict(value)
    if isinstance(data, dict) and isinstance(data.get(key), dict):
        return dict(data.get(key) or {})
    return {}


def _extract_optional_int(source: Dict[str, Any], data: Any, key: str) -> Optional[int]:
    value = source.get(key)
    if isinstance(value, int):
        return value
    if isinstance(data, dict) and isinstance(data.get(key), int):
        return data.get(key)
    return None


def _build_summary(tool_name: str, payload: Dict[str, Any], data: Any, ok: bool) -> str:
    explicit = _first_text(payload.get("summary"), payload.get("message"), payload.get("detail"))
    if explicit:
        return explicit

    if not ok:
        return _first_text(payload.get("error_message"), payload.get("error_code"), f"{tool_name} 执行失败。") or f"{tool_name} 执行失败。"

    if isinstance(data, dict):
        if isinstance(data.get("layer_count"), int):
            return f"已读取 {data.get('layer_count')} 个图层。"
        if isinstance(data.get("entity_count"), int):
            return f"已读取图纸摘要，实体数 {data.get('entity_count')}。"
        if isinstance(data.get("affected_entities_count"), int):
            return f"已执行 {data.get('affected_entities_count')} 个绘图实体。"
        if isinstance(data.get("command_count"), int) and data.get("dry_run") is True:
            return f"已验证 {data.get('command_count')} 条待应用命令。"
        if data.get("bridge") is not None or data.get("autocad") is not None:
            return "已完成 CAD 健康检查。"
        if data.get("layer"):
            return f"已确认图层 {data.get('layer')}。"

    execution_log = payload.get("execution_log")
    if isinstance(execution_log, list):
        for entry in execution_log:
            text = _first_text(entry)
            if text:
                return text

    return f"{tool_name} 执行成功。"


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
