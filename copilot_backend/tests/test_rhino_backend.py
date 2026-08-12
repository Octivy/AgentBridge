"""Unit tests for the Rhino backend using a fake ``rhinoscriptsyntax`` module."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FakeRhino:
    def __init__(self) -> None:
        self.objects = [f"obj-{index}" for index in range(3)]
        self.deleted = []

    def Objects(self):
        return list(self.objects)

    def LayerNames(self):
        return ["Layer 0", "Walls"]

    def DocumentName(self):
        return "test.3dm"

    def AddBox(self, corners):
        return "guid-box-1"

    def ObjectName(self, guid, name):
        return None

    def DeleteObject(self, guid):
        self.deleted.append(guid)
        return True


def _load_backend(fake_rs):
    path = Path(__file__).resolve().parents[2] / "adapters" / "rhino" / "backend.py"
    previous = sys.modules.pop("rhinoscriptsyntax", None)
    sys.modules["rhinoscriptsyntax"] = fake_rs
    spec = importlib.util.spec_from_file_location("rhino_backend_ut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if previous is None:
        sys.modules.pop("rhinoscriptsyntax", None)
    else:
        sys.modules["rhinoscriptsyntax"] = previous
    return module


class TestRhinoBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.rhino = FakeRhino()
        self.backend = _load_backend(self.rhino)

    def test_tool_contract_shape(self) -> None:
        tools = {tool["tool_name"]: tool for tool in self.backend.TOOLS}
        self.assertEqual(set(tools), {"rhino_scene_summary", "rhino_create_box"})
        self.assertEqual(tools["rhino_scene_summary"]["side_effect_level"], "none")
        self.assertTrue(tools["rhino_create_box"]["dry_run_supported"])
        self.assertTrue(tools["rhino_create_box"]["rollback_supported"])

    def test_scene_summary(self) -> None:
        result = self.backend.scene_summary()
        self.assertEqual(result["object_count"], 3)
        self.assertEqual(result["document"], "test.3dm")
        self.assertEqual(result["layers"], ["Layer 0", "Walls"])

    def test_create_box_dry_run_apply_rollback(self) -> None:
        backend = self.backend
        dry = backend.create_box({"name": "BoxA", "size": [2, 3, 4], "location": [0, 0, 0]}, True)
        self.assertTrue(dry["ok"])
        self.assertEqual(dry["result"]["preview"]["corner_count"], 8)
        self.assertEqual(dry["result"]["preview"]["object_name"], "BoxA")

        applied = backend.create_box({"name": "BoxA", "size": [2, 3, 4], "location": [0, 0, 0]}, False)
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["rollback_token"], "rhino-box-BoxA")

        rolled = backend.rollback(applied["rollback_token"])
        self.assertTrue(rolled["ok"])
        self.assertTrue(rolled["result"]["rolled_back"])
        self.assertEqual(self.rhino.deleted, ["guid-box-1"])

    def test_create_box_validation(self) -> None:
        result = self.backend.create_box({"size": [1, 2], "location": [0, 0, 0]}, True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")

    def test_rollback_unknown(self) -> None:
        result = self.backend.rollback("rhino-unknown")
        self.assertFalse(result["ok"])
