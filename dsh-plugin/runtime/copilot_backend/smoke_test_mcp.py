"""Live smoke test for the current 13-tool CAD MCP product contract."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.tool_executor import CadToolExecutor
from cadmcp.result_protocol import STANDARD_TOOL_RESULT_SCHEMA, build_tool_error_result


REQUIRED_FIELDS = tuple(STANDARD_TOOL_RESULT_SCHEMA["required"])
ALLOWED_FIELDS = set(STANDARD_TOOL_RESULT_SCHEMA["properties"])


def parse_result(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return build_tool_error_result("unknown", "invalid_json", f"Non-JSON tool result: {text}")


def validate_result_protocol(payload, *, expected_tool_name: str, expected_dry_run):
    errors = []
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    extra = sorted(set(payload) - ALLOWED_FIELDS)
    if extra:
        errors.append(f"unexpected fields: {', '.join(extra)}")
    if not isinstance(payload.get("ok"), bool):
        errors.append("ok must be a boolean")
    if payload.get("tool_name") != expected_tool_name:
        errors.append(f"tool_name mismatch: expected {expected_tool_name}, got {payload.get('tool_name')}")
    if not isinstance(payload.get("summary"), str):
        errors.append("summary must be a string")
    if payload.get("dry_run") is not None and not isinstance(payload.get("dry_run"), bool):
        errors.append("dry_run must be a boolean or null")
    elif payload.get("ok") is True and expected_dry_run is not None and payload.get("dry_run") is not expected_dry_run:
        errors.append(f"dry_run mismatch: expected {expected_dry_run}, got {payload.get('dry_run')}")
    if payload.get("ok") is False:
        if not str(payload.get("error_code") or "").strip():
            errors.append("failed results must include error_code")
        if not str(payload.get("error_message") or "").strip():
            errors.append("failed results must include error_message")
    return errors


READ_CALLS = [
    ("cad_health_check", {}),
    ("list_layers", {}),
    ("get_drawing_snapshot", {}),
    ("arch_get_drawing_context", {}),
    ("arch_recognize_functional_objects", {}),
    ("arch_suggest_layer_mapping", {}),
]

WRITE_CALLS = [
    ("ensure_layer", {"layer": "MCP_SMOKE", "color": 3}),
    ("draw_line", {"start": [0, 0], "end": [1200, 0], "layer": "MCP_SMOKE"}),
    (
        "execute_draw_batch",
        {"commands": [{"type": "LINE", "start": [0, 0], "end": [800, 800], "layer": "MCP_SMOKE"}]},
    ),
    (
        "arch_draw_outer_outline",
        {"boundary": [[0, 0], [2400, 0], [2400, 1600], [0, 1600]], "layer": "MCP_SMOKE"},
    ),
    (
        "arch_apply_layer_mapping",
        {"mappings": [{"source_layer": "MCP_SMOKE", "target_layer": "AI-OUTLINE", "entity_count": 0}]},
    ),
]


async def run(apply_writes: bool) -> int:
    executor = CadToolExecutor()
    failed = False
    for tool_name, arguments in READ_CALLS:
        result = await executor.execute_tool(tool_name, arguments, caller="live_smoke")
        print(json.dumps(result, ensure_ascii=False))
        failed = failed or not bool(result.get("ok"))
        if tool_name == "cad_health_check" and not result.get("ok"):
            return 1

    for tool_name, arguments in WRITE_CALLS:
        preview = await executor.execute_tool(tool_name, arguments, caller="live_smoke", dry_run=True)
        print(json.dumps(preview, ensure_ascii=False))
        if not preview.get("ok"):
            failed = True
            continue
        if apply_writes:
            commit = await executor.execute_tool(
                tool_name,
                {
                    **arguments,
                    "permission_token": preview.get("permission_token"),
                    "preview_hash": preview.get("preview_hash"),
                    "permission_request_id": preview.get("permission_request_id"),
                    "confirmed_by_local_user": True,
                    "task_id": "live-smoke",
                },
                caller="live_smoke",
                dry_run=False,
            )
            print(json.dumps(commit, ensure_ascii=False))
            failed = failed or not bool(commit.get("ok"))
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-writes", action="store_true", help="Commit previewed writes to AutoCAD.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.apply_writes)))


if __name__ == "__main__":
    main()
