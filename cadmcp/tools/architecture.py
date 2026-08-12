from __future__ import annotations

from typing import Any, Dict

from cadmcp.domain.architecture.drawing_context import build_drawing_context
from cadmcp.domain.architecture.functional_objects import recognize_functional_objects
from cadmcp.domain.architecture.layer_mapping import suggest_layer_mapping, validate_layer_mappings
from cadmcp.domain.architecture.outer_outline import extract_outer_outline


async def execute_architecture_tool(
    tool_name: str, arguments: Dict[str, Any], *, dry_run: bool = False
) -> Dict[str, Any]:
    safe = dict(arguments or {})
    if tool_name == "arch_get_drawing_context":
        return _drawing_context(safe)
    if tool_name == "arch_recognize_functional_objects":
        return _functional_objects(safe)
    if tool_name == "arch_extract_outer_outline":
        return _extract_outline(safe)
    if tool_name == "arch_draw_outer_outline":
        return _draw_outline(safe, dry_run=dry_run)
    if tool_name == "arch_suggest_layer_mapping":
        return _suggest_mapping(safe)
    if tool_name == "arch_apply_layer_mapping":
        return _apply_mapping(safe, dry_run=dry_run)
    return _error(tool_name, "unsupported_tool", f"Unsupported product tool: {tool_name}")


def _drawing_context(arguments: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = arguments.get("snapshot")
    if not isinstance(snapshot, dict):
        return _error("arch_get_drawing_context", "invalid_arguments", "snapshot is required.")
    data = build_drawing_context(
        snapshot,
        drawing_id=str(arguments.get("drawing_id") or ""),
        units=str(arguments.get("units") or ""),
    )
    return _success("arch_get_drawing_context", "图纸理解上下文已生成。", data)


def _functional_objects(arguments: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = arguments.get("snapshot")
    if not isinstance(snapshot, dict):
        return _error("arch_recognize_functional_objects", "invalid_arguments", "snapshot is required.")
    layer_arguments: dict[str, list[str] | None] = {}
    for name in ("wall_layers", "door_layers", "window_layers"):
        value = arguments.get(name)
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            return _error(
                "arch_recognize_functional_objects",
                "invalid_arguments",
                f"{name} must be an array of layer names.",
            )
        layer_arguments[name] = value
    data = recognize_functional_objects(
        snapshot,
        scope=arguments.get("scope") if isinstance(arguments.get("scope"), dict) else None,
        wall_layers=layer_arguments["wall_layers"],
        door_layers=layer_arguments["door_layers"],
        window_layers=layer_arguments["window_layers"],
    )
    counts = data["summary"]["semantic_counts"]
    return _success(
        "arch_recognize_functional_objects",
        f"已识别墙 {counts['wall']} 个、门 {counts['door']} 个、窗 {counts['window']} 个。",
        data,
    )


def _extract_outline(arguments: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = arguments.get("snapshot")
    if not isinstance(snapshot, dict):
        return _error("arch_extract_outer_outline", "invalid_arguments", "snapshot is required.")
    source_layers = arguments.get("source_layers")
    if source_layers is not None and (
        not isinstance(source_layers, list)
        or not all(isinstance(item, str) for item in source_layers)
    ):
        return _error(
            "arch_extract_outer_outline",
            "invalid_arguments",
            "source_layers must be an array of layer names.",
        )
    tolerance = arguments.get("tolerance")
    if tolerance is not None and not isinstance(tolerance, (int, float)):
        return _error("arch_extract_outer_outline", "invalid_arguments", "tolerance must be a number.")
    data = extract_outer_outline(
        snapshot,
        drawing_id=str(arguments.get("drawing_id") or ""),
        units=str(arguments.get("units") or ""),
        scope=arguments.get("scope") if isinstance(arguments.get("scope"), dict) else None,
        source_layers=source_layers,
        tolerance=float(tolerance) if tolerance is not None else None,
    )
    boundary = data["outline"]["boundary"]
    if len(boundary) < 3:
        return _error(
            "arch_extract_outer_outline",
            "outline_not_found",
            "未找到可绘制的外围闭合轮廓。" + " ".join(data.get("warnings") or []),
        )
    return _success(
        "arch_extract_outer_outline",
        f"已提取外围轮廓，面积 {data['outline']['area']} {data['outline']['area_unit']}。",
        data,
    )


def _draw_outline(arguments: Dict[str, Any], *, dry_run: bool) -> Dict[str, Any]:
    outline = arguments.get("outline")
    boundary = outline.get("boundary") if isinstance(outline, dict) else arguments.get("boundary")
    if not isinstance(boundary, list) or len(boundary) < 3 or not all(_point(item) for item in boundary):
        return _error(
            "arch_draw_outer_outline",
            "invalid_arguments",
            "outline.boundary or boundary with at least three points is required.",
        )
    layer = str(arguments.get("layer") or "AI-OUTLINE")
    object_id = str(arguments.get("object_id") or "preview-outer-outline")
    command = {"type": "POLYLINE", "layer": layer, "points": boundary, "closed": True}
    return _success(
        "arch_draw_outer_outline",
        "外围轮廓绘制预演已生成。" if dry_run else "外围轮廓已绘制。",
        {
            "object_type": "outer_outline",
            "created_object_ids": [object_id],
            "preview": {"commands": [command], "command_count": 1},
        },
        dry_run=dry_run,
        affected=0 if dry_run else 1,
    )


def _suggest_mapping(arguments: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = arguments.get("snapshot")
    if not isinstance(snapshot, dict):
        return _error("arch_suggest_layer_mapping", "invalid_arguments", "snapshot is required.")
    targets = arguments.get("target_layers")
    if targets is not None and not isinstance(targets, dict):
        return _error(
            "arch_suggest_layer_mapping", "invalid_arguments", "target_layers must be an object."
        )
    data = suggest_layer_mapping(snapshot, target_layers=targets)
    return _success(
        "arch_suggest_layer_mapping",
        f"已生成 {data['summary']['suggested_mapping_count']} 个图层映射建议。",
        data,
    )


def _apply_mapping(arguments: Dict[str, Any], *, dry_run: bool) -> Dict[str, Any]:
    try:
        mappings = validate_layer_mappings(arguments.get("mappings"))
    except (TypeError, ValueError) as exc:
        return _error("arch_apply_layer_mapping", "invalid_arguments", str(exc))
    handles = arguments.get("entity_handles")
    if handles is not None and (
        not isinstance(handles, list) or not all(isinstance(item, str) for item in handles)
    ):
        return _error(
            "arch_apply_layer_mapping", "invalid_arguments", "entity_handles must be an array of handles."
        )
    estimated = sum(item["entity_count"] for item in mappings)
    return _success(
        "arch_apply_layer_mapping",
        "图层迁移预演已生成。" if dry_run else "图层迁移已完成。",
        {
            "mappings": mappings,
            "mapping_count": len(mappings),
            "estimated_entity_count": estimated,
            "entity_handles": handles or [],
            "selection_mode": "handles" if handles else "current_space_layers",
        },
        dry_run=dry_run,
        affected=0 if dry_run else estimated,
    )


def _success(
    tool_name: str,
    summary: str,
    data: Dict[str, Any],
    *,
    dry_run: bool = False,
    affected: int = 0,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "tool_name": tool_name,
        "summary": summary,
        "dry_run": dry_run,
        "affected_entities_count": affected,
        "data": data,
        "error_code": None,
        "error_message": None,
        "request_id": None,
    }


def _error(tool_name: str, code: str, message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool_name": tool_name,
        "summary": message,
        "dry_run": False,
        "affected_entities_count": 0,
        "data": None,
        "error_code": code,
        "error_message": message,
        "request_id": None,
    }


def _point(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 2 and all(
        isinstance(item, (int, float)) for item in value[:2]
    )
