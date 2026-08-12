import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.domain.architecture.layer_mapping import suggest_layer_mapping, validate_layer_mappings
from cadmcp.tools.architecture import execute_architecture_tool


def _snapshot() -> dict:
    return {
        "layers": [
            {"name": "墙体线", "count": 2},
            {"name": "DOOR-BLOCK", "count": 1},
            {"name": "notes", "count": 1},
            {"name": "0", "count": 3},
            {"name": "A-WIND", "count": 1},
        ],
        "entities": [
            {"handle": "1", "type": "Line", "layer": "墙体线"},
            {"handle": "2", "type": "Line", "layer": "墙体线"},
            {"handle": "3", "type": "BlockReference", "layer": "DOOR-BLOCK"},
            {"handle": "4", "type": "MText", "layer": "notes"},
            {"handle": "5", "type": "Line", "layer": "0"},
            {"handle": "6", "type": "Line", "layer": "0"},
            {"handle": "7", "type": "Line", "layer": "0"},
            {"handle": "8", "type": "Line", "layer": "A-WIND"},
        ],
    }


class LayerMappingTests(unittest.IsolatedAsyncioTestCase):
    def test_suggestions_are_conservative_and_keep_unknown_layers_unmapped(self) -> None:
        result = suggest_layer_mapping(_snapshot())
        mappings = {item["source_layer"]: item for item in result["mappings"]}

        self.assertEqual(mappings["墙体线"]["target_layer"], "A-WALL")
        self.assertEqual(mappings["DOOR-BLOCK"]["target_layer"], "A-DOOR")
        self.assertEqual(mappings["notes"]["target_layer"], "A-TEXT")
        self.assertEqual(mappings["墙体线"]["entity_count"], 2)
        self.assertEqual([item["source_layer"] for item in result["unmapped_layers"]], ["0"])
        self.assertEqual(result["already_standard_layers"], ["A-WIND"])
        self.assertTrue(result["summary"]["requires_user_confirmation"])

    def test_target_layer_overrides_are_supported(self) -> None:
        result = suggest_layer_mapping(_snapshot(), target_layers={"wall": "WALL-STD"})
        wall = next(item for item in result["mappings"] if item["semantic_type"] == "wall")
        self.assertEqual(wall["target_layer"], "WALL-STD")

    def test_mapping_validation_rejects_duplicate_sources(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate source_layer"):
            validate_layer_mappings(
                [
                    {"source_layer": "WALL", "target_layer": "A-WALL"},
                    {"source_layer": "wall", "target_layer": "B-WALL"},
                ]
            )

    async def test_read_suggestion_then_write_preview_forms_confirmed_pipeline(self) -> None:
        suggestion = await execute_architecture_tool(
            "arch_suggest_layer_mapping", {"snapshot": _snapshot()}
        )
        preview = await execute_architecture_tool(
            "arch_apply_layer_mapping",
            {"mappings": suggestion["data"]["mappings"]},
            dry_run=True,
        )

        self.assertTrue(suggestion["ok"])
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["affected_entities_count"], 0)
        self.assertEqual(preview["data"]["mapping_count"], 3)
        self.assertEqual(preview["data"]["selection_mode"], "current_space_layers")


if __name__ == "__main__":
    unittest.main()
