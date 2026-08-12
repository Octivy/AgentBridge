import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cadmcp.domain.architecture.functional_objects import recognize_functional_objects
from cadmcp.tools.architecture import execute_architecture_tool


def _snapshot() -> dict:
    return {
        "drawing_summary": {"drawing_id": "functional-a", "units": "Millimeters"},
        "entities": [
            {
                "handle": "L1",
                "type": "Line",
                "layer": "A-WALL",
                "start": [0, 0],
                "end": [5000, 0],
                "bounds": {"min": [0, 0], "max": [5000, 0]},
            },
            {
                "handle": "D1",
                "type": "BlockReference",
                "layer": "A-DOOR",
                "block_name": "*U12",
                "effective_name": "M0921",
                "position": [1200, 0],
                "rotation": 0.0,
                "scale": [1, 1, 1],
                "attributes": {"WIDTH": "900"},
                "bounds": {"min": [1100, -100], "max": [2000, 900]},
            },
            {
                "handle": "W1",
                "type": "BlockReference",
                "layer": "0",
                "effective_name": "TCH_WINDOW_C1521",
                "position": [3500, 0],
                "bounds": {"min": [3400, -100], "max": [4900, 100]},
            },
            {
                "handle": "N1",
                "type": "TDbWall",
                "layer": "0",
                "bounds": {"min": [0, 0], "max": [5000, 240]},
            },
            {
                "handle": "U1",
                "type": "BlockReference",
                "layer": "FURNITURE",
                "effective_name": "TABLE_01",
                "position": [2500, 2500],
                "bounds": {"min": [2000, 2000], "max": [3000, 3000]},
            },
            {
                "handle": "P1",
                "type": "AcDbProxyEntity",
                "runtime_type": "Autodesk.AutoCAD.DatabaseServices.ProxyEntity",
                "object_class": "TCH_CUSTOM_OBJECT",
                "dxf_name": "ACAD_PROXY_ENTITY",
                "is_proxy": True,
                "is_custom_object": True,
                "object_enabler_status": "missing_or_incompatible",
                "layer": "0",
                "bounds": {"min": [6000, 0], "max": [7000, 1000]},
            },
            {
                "handle": "T1",
                "type": "DBText",
                "layer": "TEXT",
                "content": "客厅",
                "position": [2500, 2000],
                "bounds": {"min": [2400, 1900], "max": [2700, 2200]},
            },
        ],
    }


class FunctionalObjectRecognitionTests(unittest.IsolatedAsyncioTestCase):
    def test_recognizes_layer_lines_blocks_and_native_objects(self) -> None:
        result = recognize_functional_objects(_snapshot())
        objects = {item["source_handle"]: item for item in result["objects"]}

        self.assertEqual(objects["L1"]["semantic_type"], "wall")
        self.assertEqual(objects["L1"]["source_kind"], "layer_linework")
        self.assertEqual(objects["L1"]["support_status"], "supported")
        self.assertEqual(objects["D1"]["semantic_type"], "door")
        self.assertEqual(objects["D1"]["source_kind"], "block")
        self.assertEqual(objects["D1"]["block_name"], "M0921")
        self.assertEqual(objects["W1"]["semantic_type"], "window")
        self.assertEqual(objects["N1"]["semantic_type"], "wall")
        self.assertEqual(objects["N1"]["source_kind"], "native_object")
        self.assertEqual(objects["N1"]["support_status"], "degraded")
        self.assertEqual(objects["U1"]["semantic_type"], "unknown")
        self.assertEqual(objects["U1"]["support_status"], "needs_review")
        self.assertEqual(objects["P1"]["source_kind"], "proxy")
        self.assertEqual(objects["P1"]["support_status"], "unsupported")
        self.assertEqual(objects["P1"]["object_enabler_status"], "missing_or_incompatible")
        self.assertNotIn("T1", objects)
        self.assertEqual(result["summary"]["semantic_counts"]["wall"], 2)
        self.assertEqual(result["summary"]["semantic_counts"]["door"], 1)
        self.assertEqual(result["summary"]["semantic_counts"]["window"], 1)
        self.assertEqual(result["summary"]["ignored_annotation_count"], 1)
        self.assertTrue(result["summary"]["review_required"])

    def test_scope_filters_objects_before_recognition(self) -> None:
        result = recognize_functional_objects(
            _snapshot(),
            scope={"bounds": {"min": [0, -500], "max": [2100, 1000]}},
        )

        handles = {item["source_handle"] for item in result["objects"]}
        self.assertEqual(handles, {"L1", "D1", "N1"})

    def test_configured_layer_is_strong_evidence(self) -> None:
        snapshot = {
            "entities": [
                {
                    "handle": "X1",
                    "type": "BlockReference",
                    "layer": "CUSTOM-WALL",
                    "effective_name": "DOOR_SYMBOL",
                    "position": [0, 0],
                }
            ]
        }

        result = recognize_functional_objects(snapshot, wall_layers=["CUSTOM-WALL"])
        item = result["objects"][0]

        self.assertEqual(item["semantic_type"], "wall")
        self.assertEqual(item["support_status"], "supported")
        self.assertTrue(any(evidence["source"] == "configured_layer" for evidence in item["evidence"]))

    async def test_tool_returns_standard_read_only_result(self) -> None:
        result = await execute_architecture_tool(
            "arch_recognize_functional_objects",
            {"snapshot": _snapshot()},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool_name"], "arch_recognize_functional_objects")
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["affected_entities_count"], 0)
        self.assertIn("已识别墙 2 个", result["summary"])

    async def test_tool_validates_layer_arrays(self) -> None:
        result = await execute_architecture_tool(
            "arch_recognize_functional_objects",
            {"snapshot": _snapshot(), "wall_layers": "A-WALL"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
