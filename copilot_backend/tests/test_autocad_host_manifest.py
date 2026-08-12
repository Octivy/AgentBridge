import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.tool_registry import get_product_tool  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]

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


def test_autocad_manifest_matches_tool_registry():
    manifest = json.loads((ROOT / "Resources" / "autocad_tools.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    names = [entry["tool_name"] for entry in manifest["tools"]]
    assert names == CAD_BRIDGE_TOOLS
    for entry in manifest["tools"]:
        tool = get_product_tool(entry["tool_name"])
        assert tool is not None
        assert entry["input_schema"] == tool.input_schema
        assert entry["dry_run_supported"] == tool.dry_run_supported
        assert entry["side_effect_level"] == tool.side_effect_level
        assert entry["rollback_supported"] == tool.rollback_supported
        assert entry["risk_level"] == tool.risk_level
