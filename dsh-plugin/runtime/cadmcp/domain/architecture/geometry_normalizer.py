from __future__ import annotations

from typing import Any


def normalize_snapshot_geometry(snapshot: dict[str, Any], *, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = dict(snapshot or {})
    bounds = _scope_bounds(scope)
    entities = []
    for index, raw in enumerate(snapshot.get("entities") or []):
        if not isinstance(raw, dict):
            continue
        entity = normalize_entity(raw, fallback_id=f"entity-{index + 1}")
        if bounds and not _entity_intersects_bounds(entity, bounds):
            continue
        entities.append(entity)

    texts = []
    text_handles: set[str] = set()
    for index, raw in enumerate(snapshot.get("texts") or []):
        if not isinstance(raw, dict):
            continue
        text = normalize_text(raw, fallback_id=f"text-{index + 1}")
        if bounds and not _point_in_bounds(text.get("position"), bounds):
            continue
        texts.append(text)
        text_handles.add(str(text.get("handle") or ""))

    # Detailed snapshots contain text in the entity stream as well. Keeping this
    # fallback makes the parser work with both the compact legacy snapshot and the
    # richer geometry snapshot without duplicating labels.
    for entity in entities:
        if entity.get("type") != "text":
            continue
        handle = str(entity.get("handle") or "")
        if handle and handle in text_handles:
            continue
        text = normalize_text(entity, fallback_id=handle)
        if bounds and not _point_in_bounds(text.get("position"), bounds):
            continue
        texts.append(text)
        text_handles.add(handle)

    normalized["entities"] = entities
    normalized["texts"] = texts
    normalized["blocks"] = [entity for entity in entities if entity.get("type") == "block_reference"]
    normalized["dimensions"] = [entity for entity in entities if entity.get("type") == "dimension"]
    return normalized


def normalize_entity(raw: dict[str, Any], *, fallback_id: str = "") -> dict[str, Any]:
    runtime_type = str(
        raw.get("runtime_type")
        or raw.get("type_name")
        or raw.get("entity_type")
        or raw.get("type")
        or ""
    )
    entity_type = _normalize_type(runtime_type)
    entity = {
        "handle": str(raw.get("handle") or raw.get("id") or fallback_id),
        "type": entity_type,
        "runtime_type": runtime_type,
        "layer": str(raw.get("layer") or "0"),
    }
    for key in (
        "start",
        "end",
        "center",
        "position",
        "points",
        "bounds",
        "closed",
        "radius",
        "start_angle",
        "end_angle",
        "rotation",
        "scale",
        "name",
        "block_name",
        "effective_name",
        "attributes",
        "content",
        "text",
        "height",
        "text_style",
        "measurement",
        "object_class",
        "dxf_name",
        "is_proxy",
        "is_custom_object",
        "object_enabler_status",
    ):
        value = raw.get(key)
        if value is not None:
            entity[key] = value
    if "content" not in entity and raw.get("text_content") is not None:
        entity["content"] = raw.get("text_content")
    if "block_name" not in entity and raw.get("name") is not None and entity_type == "block_reference":
        entity["block_name"] = raw.get("name")
    return entity


def normalize_text(raw: dict[str, Any], *, fallback_id: str = "") -> dict[str, Any]:
    return {
        "handle": str(raw.get("handle") or raw.get("id") or fallback_id),
        "type": "text",
        "layer": str(raw.get("layer") or "0"),
        "content": str(raw.get("content") or raw.get("text") or "").strip(),
        "position": _point(raw.get("position")),
        "height": raw.get("height"),
        "rotation": raw.get("rotation"),
        "text_style": raw.get("text_style"),
    }


def explode_boundary_segments(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for entity in entities:
        entity_type = str(entity.get("type") or "")
        handle = str(entity.get("handle") or "")
        if entity_type == "line":
            start = _point(entity.get("start"))
            end = _point(entity.get("end"))
            if start and end:
                segments.append({"handle": handle, "type": "Line", "layer": entity.get("layer"), "start": start, "end": end})
            continue
        if entity_type != "polyline":
            continue
        points = [_point(point) for point in entity.get("points") or []]
        points = [point for point in points if point is not None]
        if len(points) < 2:
            continue
        pair_count = len(points) if bool(entity.get("closed")) else len(points) - 1
        for index in range(pair_count):
            start = points[index]
            end = points[(index + 1) % len(points)]
            segments.append(
                {
                    "handle": f"{handle}:{index + 1}",
                    "source_handle": handle,
                    "type": "Line",
                    "layer": entity.get("layer"),
                    "start": start,
                    "end": end,
                }
            )
    return segments


def entity_position(entity: dict[str, Any]) -> list[float] | None:
    for key in ("position", "center"):
        point = _point(entity.get(key))
        if point:
            return point
    bounds = entity.get("bounds")
    if isinstance(bounds, dict):
        minimum = _point(bounds.get("min"))
        maximum = _point(bounds.get("max"))
        if minimum and maximum:
            return [(minimum[0] + maximum[0]) / 2.0, (minimum[1] + maximum[1]) / 2.0]
    start = _point(entity.get("start"))
    end = _point(entity.get("end"))
    if start and end:
        return [(start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0]
    return None


def _normalize_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if "blockreference" in text or text in {"insert", "block_reference"}:
        return "block_reference"
    if "polyline" in text or "lwpolyline" in text:
        return "polyline"
    if "dimension" in text:
        return "dimension"
    if text in {"dbtext", "mtext", "text"}:
        return "text"
    if "line" in text:
        return "line"
    if "arc" in text:
        return "arc"
    if "circle" in text:
        return "circle"
    return text or "unknown"


def _scope_bounds(scope: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not isinstance(scope, dict):
        return None
    bounds = scope.get("bounds") if isinstance(scope.get("bounds"), dict) else scope
    minimum = _point(bounds.get("min")) if isinstance(bounds, dict) else None
    maximum = _point(bounds.get("max")) if isinstance(bounds, dict) else None
    if not minimum or not maximum:
        return None
    return (min(minimum[0], maximum[0]), min(minimum[1], maximum[1]), max(minimum[0], maximum[0]), max(minimum[1], maximum[1]))


def _entity_intersects_bounds(entity: dict[str, Any], bounds: tuple[float, float, float, float]) -> bool:
    entity_bounds = entity.get("bounds")
    if isinstance(entity_bounds, dict):
        minimum = _point(entity_bounds.get("min"))
        maximum = _point(entity_bounds.get("max"))
        if minimum and maximum:
            return not (
                max(minimum[0], maximum[0]) < bounds[0]
                or min(minimum[0], maximum[0]) > bounds[2]
                or max(minimum[1], maximum[1]) < bounds[1]
                or min(minimum[1], maximum[1]) > bounds[3]
            )
    geometry_points = [_point(entity.get(key)) for key in ("start", "end", "center", "position")]
    geometry_points.extend(_point(item) for item in entity.get("points") or [])
    geometry_points = [point for point in geometry_points if point]
    if geometry_points:
        minimum_x = min(point[0] for point in geometry_points)
        maximum_x = max(point[0] for point in geometry_points)
        minimum_y = min(point[1] for point in geometry_points)
        maximum_y = max(point[1] for point in geometry_points)
        return not (maximum_x < bounds[0] or minimum_x > bounds[2] or maximum_y < bounds[1] or minimum_y > bounds[3])
    return True


def _point_in_bounds(point: Any, bounds: tuple[float, float, float, float]) -> bool:
    value = _point(point)
    return bool(value and bounds[0] <= value[0] <= bounds[2] and bounds[1] <= value[1] <= bounds[3])


def _point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    if not isinstance(value[0], (int, float)) or not isinstance(value[1], (int, float)):
        return None
    return [float(value[0]), float(value[1])]


__all__ = ["entity_position", "explode_boundary_segments", "normalize_entity", "normalize_snapshot_geometry"]
