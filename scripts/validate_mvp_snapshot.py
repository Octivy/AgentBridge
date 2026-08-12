from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.domain.architecture.functional_objects import recognize_functional_objects
from cadmcp.domain.architecture.layer_mapping import suggest_layer_mapping
from cadmcp.domain.architecture.outer_outline import extract_outer_outline


def validate_snapshot(
    snapshot: Mapping[str, Any], expected: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    expected = dict(expected or {})
    functional = recognize_functional_objects(dict(snapshot))
    layer_mapping = suggest_layer_mapping(snapshot)
    summary = functional["summary"]
    checks: list[dict[str, Any]] = []

    reported_count = summary["functional_object_count"] + summary["ignored_annotation_count"]
    checks.append(
        _check(
            "all_snapshot_entities_accounted_for",
            reported_count == summary["source_entity_count"],
            reported_count,
            summary["source_entity_count"],
        )
    )

    proxy_objects = [
        item for item in functional["objects"] if item.get("source_kind") == "proxy"
    ]
    proxy_reporting_ok = all(
        item.get("source_handle")
        and item.get("runtime_type")
        and item.get("support_status") in {"degraded", "unsupported"}
        for item in proxy_objects
    )
    checks.append(
        _check(
            "proxy_objects_explicitly_reported",
            proxy_reporting_ok,
            len(proxy_objects),
            "all proxy objects include handle, runtime type and degraded/unsupported status",
        )
    )

    expected_counts = expected.get("semantic_counts")
    if isinstance(expected_counts, Mapping):
        for semantic_type, expected_count in expected_counts.items():
            actual = summary["semantic_counts"].get(str(semantic_type), 0)
            checks.append(
                _check(
                    f"semantic_count:{semantic_type}",
                    actual == int(expected_count),
                    actual,
                    int(expected_count),
                )
            )

    outline_data: dict[str, Any] | None = None
    outline_error: str | None = None
    try:
        extracted = extract_outer_outline(dict(snapshot))
        candidate = extracted.get("outline")
        if isinstance(candidate, dict) and len(candidate.get("boundary") or []) >= 3:
            outline_data = candidate
        else:
            outline_error = "; ".join(str(item) for item in extracted.get("warnings") or [])
    except Exception as exc:  # report fixture failures without hiding other checks
        outline_error = str(exc)

    if bool(expected.get("require_outline")):
        checks.append(
            _check(
                "outer_outline_found",
                outline_data is not None,
                outline_data is not None,
                True,
                outline_error,
            )
        )

    if expected.get("outline_area") is not None:
        expected_area = float(expected["outline_area"])
        actual_area = float((outline_data or {}).get("area") or 0.0)
        tolerance_ratio = float(expected.get("area_tolerance_ratio") or 0.01)
        tolerance = max(1e-9, abs(expected_area) * tolerance_ratio)
        checks.append(
            _check(
                "outer_outline_area",
                outline_data is not None and abs(actual_area - expected_area) <= tolerance,
                actual_area,
                expected_area,
                f"tolerance={tolerance}",
            )
        )

    expected_unmapped = expected.get("unmapped_layers")
    if isinstance(expected_unmapped, list):
        actual_unmapped = sorted(
            item["source_layer"] for item in layer_mapping["unmapped_layers"]
        )
        checks.append(
            _check(
                "unmapped_layers",
                actual_unmapped == sorted(str(item) for item in expected_unmapped),
                actual_unmapped,
                sorted(str(item) for item in expected_unmapped),
            )
        )

    return {
        "schema_version": 1,
        "ok": all(item["passed"] for item in checks),
        "drawing_id": functional.get("drawing_id") or "",
        "checks": checks,
        "functional_objects": functional,
        "outer_outline": outline_data,
        "outer_outline_error": outline_error,
        "layer_mapping": layer_mapping,
    }


def _check(
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
        "detail": detail,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an AISNAPSHOT JSON export against the stage-1 CAD MCP MVP."
    )
    parser.add_argument("snapshot", type=Path, help="Path to the snapshot JSON file")
    parser.add_argument("--expected", type=Path, help="Optional expected-result JSON file")
    parser.add_argument("--output", type=Path, help="Optional output report path")
    args = parser.parse_args(argv)

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    expected = (
        json.loads(args.expected.read_text(encoding="utf-8-sig")) if args.expected else {}
    )
    report = validate_snapshot(snapshot, expected)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
