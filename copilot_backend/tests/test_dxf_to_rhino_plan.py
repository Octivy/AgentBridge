"""Unit tests for the DXF -> Rhino plan builder (wall junctions and openings)."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "copilot_backend" / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("dxf_to_rhino_plan_ut", SCRIPTS / "dxf_to_rhino_plan.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def _box_span_mm(box, axis):
    """Return the plan span of a box in mm on the given axis."""
    size = box["size"]
    loc = box["location"]
    if axis == "x":
        half = size[0] * 500.0
        center = loc[0] * 1000.0
    else:
        half = size[1] * 500.0
        center = loc[1] * 1000.0
    return (center - half, center + half)


class TestJunctionExtension(unittest.TestCase):
    def test_extend_through_crossing_wall_to_far_face(self) -> None:
        h_walls = [(10000.0, 200.0, 5000.0, 8000.0)]
        v_walls = [(8300.0, 200.0, 9900.0, 10100.0)]
        out_h, out_v = p._extend_junctions(h_walls, v_walls)
        # h wall extends from b=8000 through the v centerline (8300) to its
        # far face (8300 + 200/2 = 8400).
        self.assertEqual(out_h[0][3], 8400.0)
        self.assertEqual(out_v, v_walls)

    def test_parallel_walls_not_merged(self) -> None:
        h_walls = [(10000.0, 200.0, 0.0, 10000.0)]
        v_walls = [(5000.0, 200.0, 11000.0, 12000.0)]
        out_h, out_v = p._extend_junctions(h_walls, v_walls)
        self.assertEqual(out_h, h_walls)
        self.assertEqual(out_v, v_walls)


class TestOpeningCuts(unittest.TestCase):
    def test_door_cuts_every_overlapping_wall_run(self) -> None:
        # Two horizontal runs on the same centerline with a 1000mm door
        # spanning 40900..41900 (door center 41400): the door zone overlaps
        # both runs, so BOTH must be cut (the right run keeps only its
        # part beyond 41900).
        segments = [
            {"kind": "h", "x1": 40000.0, "x2": 40900.0, "y1": 8100.0, "y2": 8100.0, "thick": 200.0},
            {"kind": "h", "x1": 41300.0, "x2": 42050.0, "y1": 8100.0, "y2": 8100.0, "thick": 200.0},
        ]
        openings = [
            {
                "kind": "door",
                "layer": "DOOR_FIRE",
                "width_mm": 1000.0,
                "height_mm": 2200.0,
                "p1": (41400.0, 8100.0),
                "angle": 0.0,
            }
        ]
        plan, origin_x, origin_y = p.build_plan(segments, [], openings, 3.0)
        self.assertEqual(origin_x, 40000.0)
        self.assertEqual(origin_y, 8100.0)
        # Door zone 40900..41900 in absolute mm -> 900..1900 relative.
        door_zone = (900.0, 1900.0)
        full_walls = [b for b in plan if b["layer"] == "墙" and b["size"][2] == 3.0]
        intruding = []
        for box in full_walls:
            x0, x1 = _box_span_mm(box, "x")
            y0, y1 = _box_span_mm(box, "y")
            # A full-height wall that overlaps the door zone in plan (with a
            # small epsilon for shared faces).
            if x1 > door_zone[0] + 1.0 and x0 < door_zone[1] - 1.0 and y0 < 100.0 and y1 > -100.0:
                intruding.append(box["name"])
        self.assertEqual(intruding, [])
        # The right run keeps its sliver beyond the door.
        names = [b["name"] for b in full_walls]
        self.assertTrue(any("41900" in name and "42050" in name for name in names))
        # Door marker and lintel still emitted once.
        door_boxes = [b for b in plan if b["layer"] == "门"]
        lintels = [b for b in plan if b["name"].startswith("楣")]
        self.assertEqual(len(door_boxes), 1)
        self.assertEqual(len(lintels), 1)

    def test_real_t3_file_smoke(self) -> None:
        dxf = ROOT / "Tsetfile" / "一层平面图_t3门墙柱.dxf"
        if not dxf.exists():
            self.skipTest("T3 test file not present")
        doc = p.ezdxf.readfile(str(dxf))
        segments, columns, openings = p._parse_t3(doc)
        plan, origin_x, origin_y = p.build_plan(segments, columns, openings, 3.0)
        self.assertGreater(len(plan), 100)
        self.assertTrue(any(b["layer"] == "墙" for b in plan))
        self.assertTrue(any(b["layer"] == "门" for b in plan))
        self.assertTrue(any(b["layer"] == "柱" for b in plan))
        self.assertIsInstance(origin_x, float)
        self.assertIsInstance(origin_y, float)

    def test_opening_only_cuts_overlapping_run(self) -> None:
        # Two runs on the same line: the opening zone (41400..42400) overlaps
        # only the right run (41300..42050). The left run (40000..40900) must
        # stay whole -- no phantom span crossing the gap between runs.
        segments = [
            {"kind": "h", "x1": 40000.0, "x2": 40900.0, "y1": 8100.0, "y2": 8100.0, "thick": 200.0},
            {"kind": "h", "x1": 41300.0, "x2": 42050.0, "y1": 8100.0, "y2": 8100.0, "thick": 200.0},
        ]
        openings = [
            {
                "kind": "window",
                "layer": "WINDOW",
                "width_mm": 1000.0,
                "height_mm": 1500.0,
                "p1": (41900.0, 8100.0),
                "angle": 0.0,
            }
        ]
        plan, origin_x, _ = p.build_plan(segments, [], openings, 3.0)
        full_walls = [b for b in plan if b["layer"] == "墙" and b["size"][2] == 3.0]
        self.assertEqual(origin_x, 40000.0)
        spans = set()
        for box in full_walls:
            x0, x1 = _box_span_mm(box, "x")
            spans.add((x0, x1))
        # Left run stays whole (0..900 relative); right run keeps (1300..1400).
        self.assertIn((0.0, 900.0), spans)
        self.assertIn((1300.0, 1400.0), spans)
        # No phantom span crosses the 40900..41300 gap.
        self.assertNotIn((0.0, 1400.0), spans)

    def test_vwall_opening_placed_on_wall(self) -> None:
        # 竖直墙上的开孔：楣/台/窗标记必须落在墙线位置 (x=fixed)，
        # 而不是被转置到 (pos, fixed)。
        segments = [
            {"kind": "v", "x1": 10000.0, "x2": 10000.0, "y1": 0.0, "y2": 10000.0, "thick": 200.0},
        ]
        openings = [
            {
                "kind": "window",
                "layer": "WINDOW",
                "width_mm": 1000.0,
                "height_mm": 1500.0,
                "p1": (10000.0, 5000.0),
                "angle": 0.0,
            }
        ]
        plan, origin_x, origin_y = p.build_plan(segments, [], openings, 3.0)
        self.assertEqual(origin_x, 10000.0)
        self.assertEqual(origin_y, 0.0)
        markers = [b for b in plan if b["layer"] == "窗"]
        lintels = [b for b in plan if b["name"].startswith("楣")]
        sills = [b for b in plan if b["name"].startswith("台")]
        self.assertEqual(len(markers), 1)
        self.assertEqual(len(lintels), 1)
        self.assertEqual(len(sills), 1)
        for box in markers + lintels + sills:
            # 位于墙线上（x 相对原点为 0），开孔中心 y 相对原点为 5m
            self.assertAlmostEqual(box["location"][0], 0.0, places=3)
            self.assertAlmostEqual(box["location"][1], 5.0, places=3)

    def test_entrance_correction_window_becomes_door(self) -> None:
        # 北侧主入口位置（校正清单里标为 door）：即使图纸画成 WINDOW，
        # 也应生成门（门图层、落地、高 2.2），而不是窗（有窗台、1.5 高）。
        segments = [
            {"kind": "h", "x1": 40658000.0, "x2": 40669731.0, "y1": 3316735.6, "y2": 3316735.6, "thick": 200.0},
            {"kind": "h", "x1": 40671531.0, "x2": 40676000.0, "y1": 3316735.6, "y2": 3316735.6, "thick": 200.0},
        ]
        openings = [
            {
                "kind": "window",
                "layer": "WINDOW",
                "width_mm": 1800.0,
                "height_mm": 1500.0,
                "p1": (40669730.8, 3316735.6),
                "angle": 0.0,
            }
        ]
        plan, _, _ = p.build_plan(segments, [], openings, 3.0)
        doors = [b for b in plan if b["layer"] == "门"]
        windows = [b for b in plan if b["layer"] == "窗"]
        self.assertEqual(len(doors), 1)
        self.assertEqual(len(windows), 0)
        door = doors[0]
        self.assertAlmostEqual(door["size"][2], 2.2, places=3)
        # 门落地：z 从 0 开始（location z = 高度一半）
        self.assertAlmostEqual(door["location"][2], 1.1, places=3)
        # 不应生成窗台
        self.assertEqual([b for b in plan if b["name"].startswith("台")], [])


if __name__ == "__main__":
    unittest.main()
