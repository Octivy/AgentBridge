from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping


DEFAULT_TARGET_LAYERS: Dict[str, Dict[str, Any]] = {
    "wall": {"name": "A-WALL", "color": 9},
    "door": {"name": "A-DOOR", "color": 1},
    "window": {"name": "A-WIND", "color": 4},
    "axis": {"name": "A-AXIS", "color": 1},
    "dimension": {"name": "A-DIMS", "color": 3},
    "text": {"name": "A-TEXT", "color": 7},
}

_LAYER_TOKENS = {
    "door": ("DOOR", "门"),
    "window": ("WINDOW", "WIND", "窗"),
    "wall": ("WALL", "墙"),
    "axis": ("AXIS", "GRID", "DOTE", "轴"),
    "dimension": ("DIM", "尺寸", "标注"),
    "text": ("TEXT", "TXT", "ANNO", "文字"),
}


def suggest_layer_mapping(
    snapshot: Mapping[str, Any],
    *,
    target_layers: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Suggest conservative source-to-target layer mappings.

    The function never guesses for an unknown layer. Suggestions are based on
    explicit layer-name tokens first and homogeneous entity types second.
    """

    targets = _build_targets(target_layers)
    target_names = {item["name"].upper() for item in targets.values()}
    entity_counts: Counter[str] = Counter()
    declared_counts: Counter[str] = Counter()
    entity_types: Dict[str, Counter[str]] = defaultdict(Counter)
    source_names: Dict[str, str] = {}

    for layer in snapshot.get("layers") or []:
        if not isinstance(layer, Mapping):
            continue
        name = str(layer.get("name") or "").strip()
        if not name:
            continue
        key = name.upper()
        source_names[key] = name
        count = layer.get("count")
        if isinstance(count, (int, float)):
            declared_counts[key] = max(declared_counts[key], int(count))

    for entity in snapshot.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        layer = str(entity.get("layer") or "").strip()
        if not layer:
            continue
        key = layer.upper()
        source_names.setdefault(key, layer)
        entity_counts[key] += 1
        entity_type = str(entity.get("type") or entity.get("runtime_type") or "").upper()
        if entity_type:
            entity_types[key][entity_type] += 1

    mappings: List[Dict[str, Any]] = []
    unmapped: List[Dict[str, Any]] = []
    already_standard: List[str] = []
    for key in sorted(source_names):
        source = source_names[key]
        entity_count = entity_counts[key] or declared_counts[key]
        if key in target_names:
            already_standard.append(source)
            continue

        semantic_type, confidence, evidence = _classify_layer(source, entity_types[key])
        target = targets.get(semantic_type)
        if target is None:
            unmapped.append(
                {
                    "source_layer": source,
                    "entity_count": entity_count,
                    "reason": "no_reliable_semantic_evidence",
                }
            )
            continue

        mappings.append(
            {
                "source_layer": source,
                "target_layer": target["name"],
                "target_color": target["color"],
                "semantic_type": semantic_type,
                "entity_count": entity_count,
                "confidence": confidence,
                "evidence": evidence,
                "status": "suggested",
            }
        )

    return {
        "schema_version": 1,
        "mappings": mappings,
        "unmapped_layers": unmapped,
        "already_standard_layers": already_standard,
        "target_layers": targets,
        "summary": {
            "suggested_mapping_count": len(mappings),
            "estimated_entity_count": sum(item["entity_count"] for item in mappings),
            "unmapped_layer_count": len(unmapped),
            "already_standard_layer_count": len(already_standard),
            "requires_user_confirmation": bool(mappings),
        },
    }


def validate_layer_mappings(mappings: Any) -> List[Dict[str, Any]]:
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("mappings must be a non-empty array")

    normalized: List[Dict[str, Any]] = []
    seen_sources = set()
    for index, item in enumerate(mappings):
        if not isinstance(item, Mapping):
            raise ValueError(f"mappings[{index}] must be an object")
        source = str(item.get("source_layer") or "").strip()
        target = str(item.get("target_layer") or "").strip()
        if not source or not target:
            raise ValueError(f"mappings[{index}] requires source_layer and target_layer")
        source_key = source.upper()
        if source_key in seen_sources:
            raise ValueError(f"duplicate source_layer: {source}")
        seen_sources.add(source_key)
        if source_key == target.upper():
            continue
        color = item.get("target_color")
        if color is not None and (not isinstance(color, int) or color < 1 or color > 255):
            raise ValueError(f"mappings[{index}].target_color must be an integer from 1 to 255")
        normalized.append(
            {
                "source_layer": source,
                "target_layer": target,
                "target_color": color if color is not None else 7,
                "semantic_type": str(item.get("semantic_type") or "unknown"),
                "entity_count": max(0, int(item.get("entity_count") or 0)),
            }
        )

    if not normalized:
        raise ValueError("mappings contains no layer changes")
    return normalized


def _build_targets(overrides: Mapping[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    targets = {key: dict(value) for key, value in DEFAULT_TARGET_LAYERS.items()}
    if not isinstance(overrides, Mapping):
        return targets
    for semantic_type, value in overrides.items():
        if semantic_type not in targets:
            continue
        if isinstance(value, str) and value.strip():
            targets[semantic_type]["name"] = value.strip()
        elif isinstance(value, Mapping):
            name = str(value.get("name") or "").strip()
            if name:
                targets[semantic_type]["name"] = name
            color = value.get("color")
            if isinstance(color, int) and 1 <= color <= 255:
                targets[semantic_type]["color"] = color
    return targets


def _classify_layer(source: str, types: Counter[str]) -> tuple[str, float, List[str]]:
    normalized = source.upper()
    for semantic_type, tokens in _LAYER_TOKENS.items():
        matched = next((token for token in tokens if token.upper() in normalized), None)
        if matched:
            return semantic_type, 0.95, [f"layer_name_token:{matched}"]

    if types and sum(types.values()) > 0:
        type_names = set(types)
        if all("TEXT" in name or "MTEXT" in name for name in type_names):
            return "text", 0.8, ["homogeneous_entity_type:text"]
        if all("DIMENSION" in name for name in type_names):
            return "dimension", 0.8, ["homogeneous_entity_type:dimension"]
    return "unknown", 0.0, []
