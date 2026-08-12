import unittest

from cadmcp.domain.architecture.drawing_context import build_drawing_context


class DrawingContextTests(unittest.TestCase):
    def test_normalizes_current_mvp_snapshot_sections(self) -> None:
        snapshot = {
            "drawing_summary": {
                "drawing_id": "plan-1",
                "units": "mm",
                "bounds": {"min": [0, 0], "max": [6000, 4000]},
            },
            "layers": [{"name": "A-WALL", "count": 1}, {"name": "A-TEXT", "count": 1}],
            "entities": [
                {"handle": "1", "type": "Line", "layer": "A-WALL"},
                {
                    "handle": "2",
                    "type": "ProxyEntity",
                    "layer": "TCH-WALL",
                    "runtime_type": "Autodesk.AutoCAD.DatabaseServices.ProxyEntity",
                    "is_proxy": True,
                    "object_enabler_status": "missing_or_incompatible",
                },
            ],
            "blocks": [{"handle": "3", "effective_name": "DOOR-900"}],
            "texts": [{"handle": "4", "content": "客厅"}],
            "dimensions": [{"handle": "5", "measurement": 6000}],
        }

        context = build_drawing_context(snapshot)

        self.assertEqual(context["drawing_id"], "plan-1")
        self.assertEqual(context["units"], "mm")
        self.assertEqual(context["semantic_groups"]["plan"], ["A-WALL"])
        self.assertEqual(context["semantic_groups"]["annotation"], ["A-TEXT"])
        self.assertEqual(context["summary"]["entity_count"], 2)
        self.assertEqual(context["summary"]["unknown_object_count"], 1)
        self.assertEqual(context["unknown_objects"][0]["handle"], "2")

    def test_reports_missing_sections_without_guessing(self) -> None:
        context = build_drawing_context({"drawing_summary": {}}, drawing_id="empty")

        self.assertEqual(context["drawing_id"], "empty")
        self.assertEqual(context["layers"], [])
        self.assertIn("snapshot contains no layers", context["warnings"])
        self.assertIn("snapshot contains no entities", context["warnings"])


if __name__ == "__main__":
    unittest.main()
