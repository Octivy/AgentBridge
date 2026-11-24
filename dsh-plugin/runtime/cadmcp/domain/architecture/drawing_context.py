from __future__ import annotations

from typing import Any, Dict, List


def build_drawing_context(
    snapshot: Dict[str, Any], *, drawing_id: str = "", units: str = ""
) -> Dict[str, Any]:
    safe = dict(snapshot or {})
    drawing_summary = _dict(safe.get("drawing_summary"))
    layers = _dict_list(safe.get("layers"))
    entities = _dict_list(safe.get("entities"))
    blocks = _dict_list(safe.get("blocks"))
    texts = _dict_list(safe.get("texts"))
    dimensions = _dict_list(safe.get("dimensions"))
    warnings: List[str] = []
    if not layers:
        warnings.append("snapshot contains no layers")
    if not entities:
        warnings.append("snapshot contains no entities")

    normalized_layers = []
    semantic_groups: Dict[str, List[str]] = {}
    for item in layers:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        layer = dict(item)
        group = str(item.get("semantic_group") or _layer_group(name)).strip()
        layer["name"] = name
        layer["semantic_group"] = group
        normalized_layers.append(layer)
        if group:
            semantic_groups.setdefault(group, []).append(name)

    unknown_objects = [
        item
        for item in entities
        if bool(item.get("is_proxy"))
        or str(item.get("object_enabler_status") or "") == "missing_or_incompatible"
    ]
    resolved_drawing_id = str(
        drawing_id or drawing_summary.get("drawing_id") or safe.get("drawing_id") or ""
    )
    resolved_units = str(units or drawing_summary.get("units") or safe.get("units") or "unitless")
    return {
        "schema_version": 1,
        "drawing_id": resolved_drawing_id,
        "units": resolved_units,
        "extents": drawing_summary.get("bounds"),
        "layers": normalized_layers,
        "semantic_groups": semantic_groups,
        "entities": entities,
        "blocks": blocks,
        "texts": texts,
        "dimensions": dimensions,
        "unknown_objects": unknown_objects,
        "summary": {
            "layer_count": len(normalized_layers),
            "entity_count": len(entities),
            "block_count": len(blocks),
            "text_count": len(texts),
            "dimension_count": len(dimensions),
            "unknown_object_count": len(unknown_objects),
        },
        "warnings": warnings,
    }


def _layer_group(name: str) -> str:
    normalized = name.upper()
    if any(token in normalized for token in ("WALL", "DOOR", "WIND", "AXIS", "墙", "门", "窗", "轴")):
        return "plan"
    if any(token in normalized for token in ("TEXT", "DIM", "ANNO", "文字", "标注")):
        return "annotation"
    return ""


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list(value: Any) -> List[Dict[str, Any]]:
    return [dict(item) for item in value or [] if isinstance(item, dict)]
