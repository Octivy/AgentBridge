import unittest

from cadmcp.domain.architecture.outer_outline import extract_outer_outline
from cadmcp.tools.architecture import execute_architecture_tool


def _snapshot() -> dict:
    return {
        "drawing_summary": {"drawing_id": "outline-1", "units": "m"},
        "layers": [{"name": "A-WALL", "count": 5}],
        "entities": [
            {"handle": "1", "type": "Line", "layer": "A-WALL", "start": [0, 0], "end": [10, 0]},
            {"handle": "2", "type": "Line", "layer": "A-WALL", "start": [10, 0], "end": [10, 4]},
            {"handle": "3", "type": "Line", "layer": "A-WALL", "start": [10, 4], "end": [0, 4]},
            {"handle": "4", "type": "Line", "layer": "A-WALL", "start": [0, 4], "end": [0, 0]},
            {"handle": "5", "type": "Line", "layer": "A-WALL", "start": [5, 0], "end": [5, 4]},
        ],
    }


class OuterOutlineTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_only_largest_outer_boundary(self) -> None:
        result = extract_outer_outline(_snapshot())

        self.assertEqual(result["model_type"], "outer_outline")
        self.assertEqual(result["outline"]["area"], 40.0)
        self.assertNotIn("spaces", result)
        self.assertNotIn("drawing", result)

    async def test_read_then_preview_pipeline_draws_one_polyline(self) -> None:
        extracted = await execute_architecture_tool(
            "arch_extract_outer_outline", {"snapshot": _snapshot()}
        )
        preview = await execute_architecture_tool(
            "arch_draw_outer_outline",
            {"outline": extracted["data"]["outline"]},
            dry_run=True,
        )

        self.assertTrue(extracted["ok"])
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["data"]["preview"]["command_count"], 1)
        self.assertTrue(preview["data"]["preview"]["commands"][0]["closed"])


if __name__ == "__main__":
    unittest.main()
