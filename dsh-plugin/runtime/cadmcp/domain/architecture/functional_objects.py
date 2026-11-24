from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from cadmcp.domain.architecture.geometry_normalizer import normalize_snapshot_geometry


FUNCTIONAL_OBJECT_SCHEMA_VERSION = 1
_STANDARD_GEOMETRY_TYPES = {"line", "polyline", "arc", "circle"}
_IGNORED_TYPES = {"text", "dimension"}
_SEMANTIC_TOKENS = {
    "door": ("DOOR", "TCH_DOOR", "门"),
    "window": ("WINDOW", "WIND", "TCH_WINDOW", "窗"),
    "wall": ("WALL", "TCH_WALL", "墙"),
}


@dataclass(frozen=True)
class FunctionalObject:
    object_id: str
    source_handle: str
    semantic_type: str
    source_kind: str
    layer: str
    block_name: str = ""
    runtime_type: str = ""
    object_class: str = ""
    dxf_name: str = ""
    object_enabler_status: str = ""
    geometry_or_bounds: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    support_status: str = "unsupported"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("object_id")
        payload["confidence"] = round(max(0.0, min(1.0, float(self.confidence))), 4)
        return payload


def recognize_functional_objects(
    snapshot: dict[str, Any],
    *,
    scope: dict[str, Any] | None = None,
    wall_layers: Iterable[str] | None = None,
    door_layers: Iterable[str] | None = None,
    window_layers: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_snapshot_geometry(snapshot, scope=scope)
    configured_layers = {
        "wall": _normalized_names(wall_layers),
        "door": _normalized_names(door_layers),
        "window": _normalized_names(window_layers),
    }
    objects: list[FunctionalObject] = []
    ignored_count = 0

    for index, entity in enumerate(normalized.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type") or "unknown")
        if entity_type in _IGNORED_TYPES:
            ignored_count += 1
            continue
        objects.append(
            _recognize_entity(
                entity,
                index=index,
                configured_layers=configured_layers,
            )
        )

    payloads = [item.to_dict() for item in objects]
    counts = {
        semantic_type: sum(1 for item in objects if item.semantic_type == semantic_type)
        for semantic_type in ("wall", "door", "window", "outline", "unknown")
    }
    support_counts = {
        status: sum(1 for item in objects if item.support_status == status)
        for status in ("supported", "degraded", "unsupported", "needs_review")
    }
    drawing_summary = normalized.get("drawing_summary")
    if not isinstance(drawing_summary, dict):
        drawing_summary = {}

    return {
        "schema_version": FUNCTIONAL_OBJECT_SCHEMA_VERSION,
        "drawing_id": str(drawing_summary.get("drawing_id") or snapshot.get("drawing_id") or ""),
        "units": str(drawing_summary.get("units") or snapshot.get("units") or ""),
        "scope": dict(scope or {}),
        "objects": payloads,
        "summary": {
            "source_entity_count": len(normalized.get("entities") or []),
            "functional_object_count": len(objects),
            "ignored_annotation_count": ignored_count,
            "semantic_counts": counts,
            "support_counts": support_counts,
            "review_required": bool(
                support_counts["unsupported"] or support_counts["needs_review"]
            ),
        },
    }


def _recognize_entity(
    entity: dict[str, Any],
    *,
    index: int,
    configured_layers: dict[str, set[str]],
) -> FunctionalObject:
    handle = str(entity.get("handle") or f"entity-{index + 1}")
    layer = str(entity.get("layer") or "0")
    entity_type = str(entity.get("type") or "unknown")
    runtime_type = str(entity.get("runtime_type") or entity_type)
    block_name = str(entity.get("effective_name") or entity.get("block_name") or "")
    source_kind = _source_kind(entity)
    evidence = _collect_evidence(
        entity,
        configured_layers=configured_layers,
        source_kind=source_kind,
    )
    scores = {"wall": 0.0, "door": 0.0, "window": 0.0}
    for item in evidence:
        semantic_type = str(item.get("semantic_type") or "")
        if semantic_type in scores:
            scores[semantic_type] += float(item.get("weight") or 0.0)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_type, best_score = ranked[0]
    second_score = ranked[1][1]
    ambiguous = best_score > 0 and second_score > 0 and best_score - second_score < 0.2
    semantic_type = "unknown" if best_score <= 0 else best_type
    confidence = _confidence(best_score, ambiguous=ambiguous, source_kind=source_kind)
    support_status = _support_status(
        semantic_type,
        source_kind=source_kind,
        ambiguous=ambiguous,
    )

    return FunctionalObject(
        object_id=f"functional-{handle}",
        source_handle=handle,
        semantic_type=semantic_type,
        source_kind=source_kind,
        layer=layer,
        block_name=block_name,
        runtime_type=runtime_type,
        object_class=str(entity.get("object_class") or ""),
        dxf_name=str(entity.get("dxf_name") or ""),
        object_enabler_status=str(entity.get("object_enabler_status") or ""),
        geometry_or_bounds=_geometry_or_bounds(entity),
        evidence=evidence,
        confidence=confidence,
        support_status=support_status,
    )


def _collect_evidence(
    entity: dict[str, Any],
    *,
    configured_layers: dict[str, set[str]],
    source_kind: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    layer = str(entity.get("layer") or "")
    normalized_layer = layer.strip().upper()
    for semantic_type, layers in configured_layers.items():
        if normalized_layer and normalized_layer in layers:
            evidence.append(
                _evidence("configured_layer", layer, semantic_type, 1.0)
            )

    fields = [
        ("layer", layer, 0.75),
        (
            "block_name",
            str(entity.get("effective_name") or entity.get("block_name") or ""),
            0.9,
        ),
        ("runtime_type", str(entity.get("runtime_type") or entity.get("type") or ""), 0.8),
        ("object_class", str(entity.get("object_class") or ""), 0.8),
        ("dxf_name", str(entity.get("dxf_name") or ""), 0.8),
    ]
    attributes = entity.get("attributes")
    if isinstance(attributes, dict):
        attribute_text = " ".join(f"{key} {value}" for key, value in attributes.items())
        fields.append(("block_attributes", attribute_text, 0.65))

    for source, value, weight in fields:
        for semantic_type in _matching_semantic_types(value):
            evidence.append(_evidence(source, value, semantic_type, weight))

    # A generic line becomes a wall candidate only when the layer carries wall
    # semantics. We deliberately do not guess from geometry alone.
    if source_kind == "layer_linework" and not any(
        item["semantic_type"] == "wall" for item in evidence
    ):
        evidence.append(
            {
                "source": "geometry_policy",
                "value": str(entity.get("type") or ""),
                "semantic_type": "unknown",
                "weight": 0.0,
                "reason": "linework_without_semantic_layer",
            }
        )
    return evidence


def _matching_semantic_types(value: Any) -> list[str]:
    text = str(value or "").strip().upper()
    if not text:
        return []
    matches: list[str] = []
    for semantic_type in ("door", "window", "wall"):
        if any(token in text for token in _SEMANTIC_TOKENS[semantic_type]):
            matches.append(semantic_type)
    return matches


def _source_kind(entity: dict[str, Any]) -> str:
    entity_type = str(entity.get("type") or "unknown")
    combined = " ".join(
        str(entity.get(key) or "")
        for key in ("type", "runtime_type", "object_class", "dxf_name")
    ).upper()
    if bool(entity.get("is_proxy")) or "PROXY" in combined:
        return "proxy"
    if entity_type == "block_reference":
        return "block"
    if entity_type in _STANDARD_GEOMETRY_TYPES:
        return "layer_linework"
    if bool(entity.get("is_custom_object")) or (entity_type and entity_type != "unknown"):
        return "native_object"
    return "unknown"


def _support_status(
    semantic_type: str,
    *,
    source_kind: str,
    ambiguous: bool,
) -> str:
    if ambiguous:
        return "needs_review"
    if source_kind == "proxy":
        return "degraded" if semantic_type != "unknown" else "unsupported"
    if source_kind == "native_object":
        return "degraded" if semantic_type != "unknown" else "unsupported"
    if semantic_type == "unknown":
        return "needs_review"
    return "supported"


def _confidence(best_score: float, *, ambiguous: bool, source_kind: str) -> float:
    if best_score <= 0:
        return 0.1
    confidence = min(0.98, 0.5 + best_score * 0.4)
    if source_kind in {"native_object", "proxy"}:
        confidence = min(confidence, 0.78)
    if ambiguous:
        confidence = min(confidence, 0.55)
    return confidence


def _geometry_or_bounds(entity: dict[str, Any]) -> dict[str, Any]:
    geometry: dict[str, Any] = {}
    for key in (
        "start",
        "end",
        "center",
        "position",
        "points",
        "closed",
        "radius",
        "rotation",
        "scale",
        "bounds",
    ):
        value = entity.get(key)
        if value is not None:
            geometry[key] = value
    return geometry


def _normalized_names(values: Iterable[str] | None) -> set[str]:
    return {
        str(item).strip().upper()
        for item in (values or [])
        if str(item).strip()
    }


def _evidence(
    source: str,
    value: str,
    semantic_type: str,
    weight: float,
) -> dict[str, Any]:
    return {
        "source": source,
        "value": value,
        "semantic_type": semantic_type,
        "weight": weight,
    }


__all__ = [
    "FUNCTIONAL_OBJECT_SCHEMA_VERSION",
    "FunctionalObject",
    "recognize_functional_objects",
]
