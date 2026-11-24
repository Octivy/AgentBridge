from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .geometry_normalizer import explode_boundary_segments, normalize_snapshot_geometry


def extract_outer_outline(
    snapshot: dict[str, Any],
    *,
    drawing_id: str = "",
    units: str = "",
    scope: dict[str, Any] | None = None,
    source_layers: list[str] | None = None,
    tolerance: float | None = None,
) -> dict[str, Any]:
    """Extract only the largest outside boundary from single-line CAD geometry."""
    normalized = normalize_snapshot_geometry(snapshot, scope=scope)
    summary = dict(normalized.get("drawing_summary") or {})
    resolved_units = str(units or summary.get("units") or "unitless").strip() or "unitless"
    resolved_tolerance = _default_tolerance(resolved_units) if tolerance is None else max(float(tolerance), 1e-9)
    entities = [item for item in normalized.get("entities") or [] if isinstance(item, dict)]
    line_entities = [item for item in entities if item.get("type") in {"line", "polyline"}]
    selected, selection = _select_source_entities(line_entities, source_layers)
    source_segments = explode_boundary_segments(selected)
    split_segments = _split_at_segment_endpoints(source_segments, resolved_tolerance)
    faces = _trace_planar_faces(split_segments, resolved_tolerance)

    bounded_faces = [face for face in faces if face["signed_area"] > resolved_tolerance * resolved_tolerance]
    outside_faces = [face for face in faces if face["signed_area"] < -(resolved_tolerance * resolved_tolerance)]
    outer_face = max(outside_faces, key=lambda item: item["area"], default=None)
    if outer_face is None and bounded_faces:
        outer_face = max(bounded_faces, key=lambda item: item["area"])
    outer_boundary = list(reversed(outer_face["boundary"])) if outer_face and outer_face["signed_area"] < 0 else list(outer_face["boundary"]) if outer_face else []

    outer_area = abs(_signed_area(outer_boundary)) if outer_boundary else 0.0
    source_bounds = _bounds_from_segments(split_segments)
    warnings: list[str] = []
    if not source_segments:
        warnings.append("未找到可用于外围轮廓分析的单线或多段线。")
    elif not outer_boundary:
        warnings.append("未识别到外围闭合轮廓，请检查端点是否相接或调整容差。")
    if len(outside_faces) > 1:
        warnings.append("检测到多个不相连的线网，当前外围轮廓取面积最大的线网。")
    if len(source_segments) >= 2000:
        warnings.append("线段数量较大，首版仅保证中小型单层平面的交互性能。")

    return {
        "schema_version": 1,
        "model_type": "outer_outline",
        "drawing_id": str(drawing_id or summary.get("drawing_id") or ""),
        "units": resolved_units,
        "scope": dict(scope or {"kind": "drawing"}),
        "selection": selection,
        "source_bounds": source_bounds,
        "outline": {
            "boundary": outer_boundary,
            "area": round(outer_area, 6),
            "area_unit": _area_unit(resolved_units),
            "area_m2": _area_m2(outer_area, resolved_units),
            "source_entity_ids": list(outer_face.get("source_entity_ids") or []) if outer_face else [],
        },
        "summary": {
            "source_entity_count": len(selected),
            "source_segment_count": len(source_segments),
            "split_segment_count": len(split_segments),
            "outer_outline_area": round(outer_area, 6),
            "area_unit": _area_unit(resolved_units),
        },
        "warnings": warnings,
    }


def _select_source_entities(
    entities: list[dict[str, Any]], source_layers: list[str] | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = {str(item).strip().lower() for item in source_layers or [] if str(item).strip()}
    if requested:
        selected = [item for item in entities if str(item.get("layer") or "").lower() in requested]
        return selected, {"mode": "explicit_layers", "layers": sorted(requested)}

    wall_tokens = ("wall", "a-wall", "墙", "tch_wall")
    wall_entities = [
        item
        for item in entities
        if any(token in str(item.get("layer") or "").lower() for token in wall_tokens)
    ]
    if wall_entities:
        return wall_entities, {
            "mode": "wall_layers",
            "layers": sorted({str(item.get("layer") or "") for item in wall_entities}),
        }
    return entities, {
        "mode": "all_linework",
        "layers": sorted({str(item.get("layer") or "") for item in entities}),
    }


def _split_at_segment_endpoints(
    segments: list[dict[str, Any]], tolerance: float
) -> list[dict[str, Any]]:
    endpoints = [list(segment[key]) for segment in segments for key in ("start", "end")]
    result: list[dict[str, Any]] = []
    for segment in segments:
        start = list(segment["start"])
        end = list(segment["end"])
        length = math.dist(start, end)
        parameter_tolerance = min(tolerance / max(length, tolerance), 0.01)
        parameters = [0.0, 1.0]
        for point in endpoints:
            parameter = _point_parameter(point, start, end, tolerance)
            if parameter is not None and parameter_tolerance < parameter < 1.0 - parameter_tolerance:
                parameters.append(parameter)
        parameters = _deduplicate_numbers(parameters, parameter_tolerance)
        for index in range(len(parameters) - 1):
            first = _interpolate(start, end, parameters[index])
            second = _interpolate(start, end, parameters[index + 1])
            if math.dist(first, second) <= tolerance:
                continue
            result.append(
                {
                    "handle": str(segment.get("source_handle") or segment.get("handle") or ""),
                    "start": first,
                    "end": second,
                    "layer": segment.get("layer"),
                }
            )
    return result


def _trace_planar_faces(segments: list[dict[str, Any]], tolerance: float) -> list[dict[str, Any]]:
    point_by_key: dict[tuple[int, int], list[float]] = {}
    point_buckets: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    edge_handles: dict[frozenset[tuple[int, int]], set[str]] = defaultdict(set)

    def snapped_key(point: list[float]) -> tuple[int, int]:
        cell = (math.floor(float(point[0]) / tolerance), math.floor(float(point[1]) / tolerance))
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                for candidate in point_buckets.get((cell[0] + x_offset, cell[1] + y_offset), []):
                    if math.dist(point, point_by_key[candidate]) <= tolerance:
                        return candidate
        key = (len(point_by_key), 0)
        point_by_key[key] = list(point)
        point_buckets[cell].append(key)
        return key

    for segment in segments:
        start_key = snapped_key(segment["start"])
        end_key = snapped_key(segment["end"])
        if start_key == end_key:
            continue
        adjacency[start_key].add(end_key)
        adjacency[end_key].add(start_key)
        handle = str(segment.get("handle") or "")
        if handle:
            edge_handles[frozenset((start_key, end_key))].add(handle)

    ordered_neighbors = {
        node: sorted(
            neighbors,
            key=lambda neighbor: math.atan2(
                point_by_key[neighbor][1] - point_by_key[node][1],
                point_by_key[neighbor][0] - point_by_key[node][0],
            ),
        )
        for node, neighbors in adjacency.items()
    }
    visited: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    faces: list[dict[str, Any]] = []
    max_steps = max(len(segments) * 4, 16)
    for start_node, neighbors in ordered_neighbors.items():
        for next_node in neighbors:
            first_edge = (start_node, next_node)
            if first_edge in visited:
                continue
            current, following = first_edge
            keys = [current]
            handles: set[str] = set()
            closed = False
            for _ in range(max_steps):
                visited.add((current, following))
                keys.append(following)
                handles.update(edge_handles.get(frozenset((current, following)), set()))
                neighbors_at_following = ordered_neighbors.get(following) or []
                if current not in neighbors_at_following:
                    break
                reverse_index = neighbors_at_following.index(current)
                candidate = neighbors_at_following[(reverse_index - 1) % len(neighbors_at_following)]
                current, following = following, candidate
                if (current, following) == first_edge:
                    closed = True
                    break
                if (current, following) in visited:
                    break
            if not closed or len(keys) < 4:
                continue
            boundary = [point_by_key[key] for key in keys]
            signed_area = _signed_area(boundary)
            if abs(signed_area) <= tolerance * tolerance:
                continue
            faces.append(
                {
                    "boundary": boundary,
                    "signed_area": signed_area,
                    "area": abs(signed_area),
                    "centroid": _centroid(boundary),
                    "source_entity_ids": sorted(handles),
                }
            )
    return faces


def _point_parameter(
    point: list[float], start: list[float], end: list[float], tolerance: float
) -> float | None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= tolerance * tolerance:
        return None
    parameter = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    if parameter < -tolerance or parameter > 1.0 + tolerance:
        return None
    projected = [start[0] + parameter * dx, start[1] + parameter * dy]
    return parameter if math.dist(point, projected) <= tolerance else None


def _deduplicate_numbers(values: list[float], tolerance: float) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
    return result


def _interpolate(start: list[float], end: list[float], parameter: float) -> list[float]:
    return [
        round(start[0] + (end[0] - start[0]) * parameter, 9),
        round(start[1] + (end[1] - start[1]) * parameter, 9),
    ]


def _signed_area(points: list[list[float]]) -> float:
    return sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points[:-1], points[1:])
    ) / 2.0


def _centroid(points: list[list[float]]) -> list[float]:
    polygon = points[:-1] if points and points[0] == points[-1] else points
    return [
        round(sum(point[0] for point in polygon) / len(polygon), 6),
        round(sum(point[1] for point in polygon) / len(polygon), 6),
    ] if polygon else []


def _bounds_from_segments(segments: list[dict[str, Any]]) -> dict[str, list[float]] | None:
    points = [segment[key] for segment in segments for key in ("start", "end")]
    if not points:
        return None
    return {
        "min": [min(point[0] for point in points), min(point[1] for point in points)],
        "max": [max(point[0] for point in points), max(point[1] for point in points)],
    }


def _default_tolerance(units: str) -> float:
    family = _unit_family(units)
    return 1.0 if family == "mm" else 0.1 if family == "cm" else 0.001


def _area_unit(units: str) -> str:
    family = _unit_family(units)
    return f"{family}2" if family else "unit2"


def _area_m2(area: float, units: str) -> float | None:
    family = _unit_family(units)
    if family == "mm":
        return round(area / 1_000_000.0, 6)
    if family == "cm":
        return round(area / 10_000.0, 6)
    return round(area, 6) if family == "m" else None


def _unit_family(units: str) -> str:
    normalized = str(units or "").strip().lower()
    if normalized in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
        return "mm"
    if normalized in {"cm", "centimeter", "centimeters", "centimetre", "centimetres"}:
        return "cm"
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    return ""




__all__ = ["extract_outer_outline"]
