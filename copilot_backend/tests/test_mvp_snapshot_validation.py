import unittest

from scripts.validate_mvp_snapshot import validate_snapshot


class MvpSnapshotValidationTests(unittest.TestCase):
    def test_validates_recognition_outline_area_and_unknown_layers(self) -> None:
        snapshot = {
            "drawing_summary": {"drawing_id": "fixture-1", "units": "m"},
            "layers": [{"name": "A-WALL", "count": 4}, {"name": "0", "count": 1}],
            "entities": [
                {"handle": "1", "type": "Line", "layer": "A-WALL", "start": [0, 0], "end": [4, 0]},
                {"handle": "2", "type": "Line", "layer": "A-WALL", "start": [4, 0], "end": [4, 3]},
                {"handle": "3", "type": "Line", "layer": "A-WALL", "start": [4, 3], "end": [0, 3]},
                {"handle": "4", "type": "Line", "layer": "A-WALL", "start": [0, 3], "end": [0, 0]},
                {"handle": "5", "type": "Circle", "layer": "0", "center": [10, 10], "radius": 1},
            ],
        }

        report = validate_snapshot(
            snapshot,
            {
                "semantic_counts": {"wall": 4},
                "require_outline": True,
                "outline_area": 12.0,
                "unmapped_layers": ["0"],
            },
        )

        self.assertTrue(report["ok"], report["checks"])
        self.assertEqual(report["drawing_id"], "fixture-1")
        self.assertEqual(report["outer_outline"]["area"], 12.0)

    def test_failed_expectation_is_visible_in_report(self) -> None:
        report = validate_snapshot(
            {"entities": []}, {"require_outline": True}
        )

        self.assertFalse(report["ok"])
        failed = [item["name"] for item in report["checks"] if not item["passed"]]
        self.assertEqual(failed, ["outer_outline_found"])


if __name__ == "__main__":
    unittest.main()
