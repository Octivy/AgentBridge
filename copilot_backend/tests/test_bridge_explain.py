import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge_explain.explain import explain_scene, explain_snapshot, explain_tool_result  # noqa: E402

SNAPSHOT = {
    "drawing_summary": {
        "total_entities": 100,
        "total_layers": 3,
        "detected_frames": 1,
        "units": "Millimeters",
        "bounds": {"min": [1000.0, 2000.0], "max": [106000.0, 76250.0]},
    },
    "layers": [
        {"name": "WALL", "semantic_group": "plan", "count": 10, "types": ["Line"]},
        {"name": "WINDOW", "semantic_group": "plan", "count": 4, "types": ["Line"]},
        {"name": "PUB_TEXT", "semantic_group": "annotation", "count": 2, "types": ["DBText"]},
    ],
    "texts": [{"content": "营业厅"}, {"content": "办公室"}],
    "blocks": [{"name": "b1", "insertions": 3}],
    "frames": [{"dominant_layers": ["WALL", "WINDOW"]}],
    "entities": [],
    "entities_truncated": False,
    "dimensions": [],
    "outside_frames": {},
}


class ExplainSnapshotTests(unittest.TestCase):
    def test_sizes_converted_to_meters(self):
        out = explain_snapshot(SNAPSHOT)
        self.assertEqual(out["size"]["width_m"], 105.0)
        self.assertEqual(out["size"]["height_m"], 74.25)
        self.assertEqual(out["size"]["width_mm"], 105000.0)

    def test_counts_and_room_labels(self):
        out = explain_snapshot(SNAPSHOT)
        self.assertEqual(out["counts"]["walls"], 10)
        self.assertEqual(out["counts"]["windows"], 4)
        self.assertEqual(out["counts"]["blocks"], 3)
        self.assertEqual(out["room_labels"], ["营业厅", "办公室"])

    def test_layer_roles_are_explained(self):
        out = explain_snapshot(SNAPSHOT)
        roles = {layer["name"]: layer["role"] for layer in out["layer_legend"]}
        self.assertEqual(roles["WALL"], "墙体结构")
        self.assertEqual(roles["WINDOW"], "窗")
        self.assertEqual(roles["PUB_TEXT"], "文字标注")

    def test_suggestions_mention_walls_and_windows(self):
        out = explain_snapshot(SNAPSHOT)
        text = " ".join(out["suggestions"])
        self.assertIn("10", text)
        self.assertIn("4", text)

    def test_scene_explanation(self):
        out = explain_scene("rhino", {"document": "d.3dm", "object_count": 12, "layers": ["A", "B"]})
        self.assertEqual(out["source"], "rhino_scene")
        self.assertEqual(out["object_count"], 12)
        self.assertEqual(out["layers"], ["A", "B"])

    def test_tool_result_dispatch_by_host_kind(self):
        out = explain_tool_result("autocad", {"ok": True, "data": {"snapshot": SNAPSHOT}})
        self.assertEqual(out["source"], "autocad_snapshot")
        self.assertEqual(out["counts"]["walls"], 10)
        out2 = explain_tool_result("rhino", {"ok": True, "data": {"object_count": 5, "layers": []}})
        self.assertEqual(out2["source"], "rhino_scene")


if __name__ == "__main__":
    unittest.main()
