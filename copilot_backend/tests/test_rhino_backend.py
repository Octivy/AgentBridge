"""Unit tests for the Rhino backend using a fake ``Rhino`` / ``Rhino.Geometry`` module."""

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FakeAttributes:
    def __init__(self, name: str = "") -> None:
        self.Name = name


class FakeRhinoObject:
    def __init__(self, guid: str) -> None:
        self.Id = guid
        self.Attributes = FakeAttributes()

    def CommitChanges(self) -> None:
        pass


class FakeObjectTable:
    def __init__(self, initial: int = 0) -> None:
        self._objects = [FakeRhinoObject("seed-%d" % index) for index in range(initial)]
        self._next_guid = 1

    def __iter__(self):
        return iter(self._objects)

    def __len__(self) -> int:
        return len(self._objects)

    def AddBrep(self, brep, attributes=None):
        del brep, attributes
        guid = "guid-box-%d" % self._next_guid
        self._next_guid += 1
        self._objects.append(FakeRhinoObject(guid))
        return guid

    def __getitem__(self, oid):
        target = str(oid)
        for obj in self._objects:
            if obj.Id == target:
                return obj
        raise KeyError(target)

    def Delete(self, oid, delete_grips=True):
        del delete_grips
        target = str(oid)
        for index, obj in enumerate(self._objects):
            if obj.Id == target:
                del self._objects[index]
                return 1
        return 0


class FakeLayer:
    def __init__(self, path: str) -> None:
        self.FullPath = path


class FakeDoc:
    def __init__(self, initial_objects: int = 0) -> None:
        self.Name = "test.3dm"
        self.Objects = FakeObjectTable(initial_objects)
        self.Layers = [FakeLayer("Layer 0"), FakeLayer("Walls")]


class FakePoint3d:
    def __init__(self, x, y, z) -> None:
        self.X = x
        self.Y = y
        self.Z = z


class FakeBoundingBox:
    def __init__(self, minimum, maximum) -> None:
        self.Min = minimum
        self.Max = maximum


class FakeBox:
    def __init__(self, bbox) -> None:
        self.BoundingBox = bbox

    def ToBrep(self):
        return "brep-1"


class FakeGeometry:
    BoundingBox = FakeBoundingBox
    Box = FakeBox
    Point3d = FakePoint3d


class FakeRhinoDoc:
    ActiveDoc = FakeDoc(3)


class FakeRhino:
    RhinoDoc = FakeRhinoDoc
    Geometry = FakeGeometry


class FakeRs:
    def DocumentName(self) -> str:
        return "test.3dm"

    def DeleteObject(self, guid) -> bool:
        return False


def _load_backend(fake_rhino, fake_rs):
    path = Path(__file__).resolve().parents[2] / "adapters" / "rhino" / "backend.py"
    previous_rhino = sys.modules.pop("Rhino", None)
    previous_rs = sys.modules.pop("rhinoscriptsyntax", None)
    sys.modules["Rhino"] = fake_rhino
    sys.modules["rhinoscriptsyntax"] = fake_rs
    spec = importlib.util.spec_from_file_location("rhino_backend_ut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if previous_rhino is None:
        sys.modules.pop("Rhino", None)
    else:
        sys.modules["Rhino"] = previous_rhino
    if previous_rs is None:
        sys.modules.pop("rhinoscriptsyntax", None)
    else:
        sys.modules["rhinoscriptsyntax"] = previous_rs
    return module


class TestRhinoBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.rhino = FakeRhino()
        self.rs = FakeRs()
        self.backend = _load_backend(self.rhino, self.rs)

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
        self.assertEqual(len(self.rhino.RhinoDoc.ActiveDoc.Objects), 4)

        rolled = backend.rollback(applied["rollback_token"])
        self.assertTrue(rolled["ok"])
        self.assertTrue(rolled["result"]["rolled_back"])
        self.assertTrue(rolled["result"]["deleted"])
        self.assertEqual(len(self.rhino.RhinoDoc.ActiveDoc.Objects), 3)

    def test_create_box_validation(self) -> None:
        result = self.backend.create_box({"size": [1, 2], "location": [0, 0, 0]}, True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")

    def test_rollback_unknown(self) -> None:
        result = self.backend.rollback("rhino-unknown")
        self.assertFalse(result["ok"])


class TestRhinoPackageSelfContained(unittest.TestCase):
    def test_package_imports_standalone(self) -> None:
        source = Path(__file__).resolve().parents[2] / "adapters" / "rhino"
        target = Path(tempfile.mkdtemp(prefix="ab-rhino-pkg-")) / "agentbridge_rhino"
        shutil.copytree(source, target)
        sys.path.insert(0, str(target))
        try:
            spec = importlib.util.spec_from_file_location("ab_rhino_bg", target / "background_host.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.main))
            self.assertTrue(callable(module.HostAdapter))
        finally:
            sys.path.remove(str(target))
