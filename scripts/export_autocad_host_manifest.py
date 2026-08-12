"""Generate Resources/autocad_tools.json from the cadmcp tool registry.

The AutoCAD host adapter serves /manifest from this file. Keeping the JSON as a
generated mirror of ``cadmcp.tool_registry`` prevents schema drift; a unit test
asserts the mirror stays in sync.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copilot_backend"))

from cadmcp.tool_registry import get_product_tool  # noqa: E402


CAD_BRIDGE_TOOLS = [
    "cad_health_check",
    "get_drawing_snapshot",
    "list_layers",
    "draw_line",
    "ensure_layer",
    "execute_draw_batch",
    "arch_draw_outer_outline",
    "arch_apply_layer_mapping",
    "cad_rollback_transaction",
]


def build_manifest() -> dict:
    tools = []
    for name in CAD_BRIDGE_TOOLS:
        tool = get_product_tool(name)
        if tool is None:
            raise SystemExit(f"missing product tool: {name}")
        tools.append(
            {
                "tool_name": tool.tool_name,
                "display_name": tool.display_name,
                "category": tool.category,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "dry_run_supported": tool.dry_run_supported,
                "side_effect_level": tool.side_effect_level,
                "result_schema": tool.result_schema,
                "risk_level": tool.risk_level,
                "rollback_supported": tool.rollback_supported,
            }
        )
    return {"schema_version": 1, "tools": tools}


def main() -> None:
    manifest = build_manifest()
    output = ROOT / "Resources" / "autocad_tools.json"
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output} with {len(manifest['tools'])} tools")


if __name__ == "__main__":
    main()
