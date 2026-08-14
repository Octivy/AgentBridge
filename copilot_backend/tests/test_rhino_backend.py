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
        self.LayerIndex = 0


class FakeRhinoObject:
    def __init__(self, guid: str) -> None:
        self.Id = guid
        self.Attributes = FakeAttributes()
        self.Geometry = FakeBrep("brep-" + guid)

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
        del brep
        guid = "guid-box-%d" % self._next_guid
        self._next_guid += 1
        obj = FakeRhinoObject(guid)
        if attributes is not None:
            obj.Attributes.LayerIndex = getattr(attributes, "LayerIndex", 0)
        self._objects.append(obj)
        return guid

    def __getitem__(self, oid):
        target = str(oid)
        for obj in self._objects:
            if obj.Id == target:
                return obj
        raise KeyError(target)

    def FindId(self, oid):
        target = str(oid)
        for obj in self._objects:
            if obj.Id == target:
                return obj
        return None

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
        self.Name = path
        self.LayerIndex = 0
        self.Color = None


class FakeLayers:
    def __init__(self) -> None:
        self._layers = [FakeLayer("Layer 0"), FakeLayer("Walls")]
        for index, layer in enumerate(self._layers):
            layer.LayerIndex = index

    def __iter__(self):
        return iter(self._layers)

    def FindName(self, name):
        for index, layer in enumerate(self._layers):
            if layer.FullPath == name:
                return index
        return -1

    def Add(self, name):
        self._layers.append(FakeLayer(name))
        index = len(self._layers) - 1
        self._layers[index].LayerIndex = index
        return index

    def __getitem__(self, index):
        return self._layers[index]


class FakeDoc:
    def __init__(self, initial_objects: int = 0) -> None:
        self.Name = "test.3dm"
        self.Objects = FakeObjectTable(initial_objects)
        self.Layers = FakeLayers()


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


class FakeBrep:
    def __init__(self, name: str) -> None:
        self.Name = name

    @staticmethod
    def CreateBooleanUnion(breps, tolerance):
        del tolerance
        return [FakeBrep("union-of-%d" % len(list(breps)))]


class FakeGeometry:
    BoundingBox = FakeBoundingBox
    Box = FakeBox
    Point3d = FakePoint3d
    Brep = FakeBrep


class FakeRhinoDoc:
    ActiveDoc = FakeDoc(3)


class FakeObjectAttributes:
    def __init__(self) -> None:
        self.LayerIndex = 0


class FakeDocObjects:
    ObjectAttributes = FakeObjectAttributes


class FakeColor:
    @staticmethod
    def FromArgb(alpha, red, green, blue):
        return (alpha, red, green, blue)


class FakeDrawing:
    Color = FakeColor


class FakeArray:
    @classmethod
    def __class_getitem__(cls, item):
        del item
        return cls

    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


class FakeSystem:
    Drawing = FakeDrawing
    Array = FakeArray


class FakeSystemDrawing:
    Color = FakeColor


class FakeRhino:
    RhinoDoc = FakeRhinoDoc
    Geometry = FakeGeometry
    DocObjects = FakeDocObjects


class FakeRs:
    def DocumentName(self) -> str:
        return "test.3dm"

    def DeleteObject(self, guid) -> bool:
        return False

    def AddLayer(self, name, color=None) -> str:
        del color
        return name

    def BooleanUnion(*args):
        del args
        return ["union-guid-1"]


def _load_backend(fake_rhino, fake_rs):
    path = Path(__file__).resolve().parents[2] / "adapters" / "rhino" / "backend.py"
    previous_rhino = sys.modules.pop("Rhino", None)
    previous_rs = sys.modules.pop("rhinoscriptsyntax", None)
    previous_system = sys.modules.pop("System", None)
    sys.modules["Rhino"] = fake_rhino
    sys.modules["rhinoscriptsyntax"] = fake_rs
    sys.modules["System"] = FakeSystem()
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
    if previous_system is not None:
        sys.modules["System"] = previous_system
    # When no real ``System`` existed before, keep the fake in ``sys.modules``
    # so backend functions that ``import System`` inside a tool call still
    # resolve during unit tests.
    return module


class TestRhinoBackend(unittest.TestCase):
    def setUp(self) -> None:
        FakeRhinoDoc.ActiveDoc = FakeDoc(3)
        self.rhino = FakeRhino()
        self.rs = FakeRs()
        self.backend = _load_backend(self.rhino, self.rs)

    def test_tool_contract_shape(self) -> None:
        tools = {tool["tool_name"]: tool for tool in self.backend.TOOLS}
        self.assertEqual(
            set(tools),
            {
                "rhino_scene_summary",
                "rhino_get_objects",
                "rhino_create_box",
                "rhino_delete_object",
                "rhino_union_layer",
            },
        )
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
        self.assertTrue(applied["rollback_token"].startswith("rhino-box-BoxA-"))
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

    def test_create_box_with_layer(self) -> None:
        sys.modules["System"] = FakeSystem()
        sys.modules["System.Drawing"] = FakeSystemDrawing()
        try:
            doc = self.rhino.RhinoDoc.ActiveDoc
            applied = self.backend.create_box(
                {"name": "BoxLayer", "size": [2, 2, 2], "location": [0, 0, 0], "layer": "WALL", "layer_color": "FF0000"},
                False,
            )
            self.assertTrue(applied["ok"])
            layer_index = doc.Layers.FindName("WALL")
            self.assertEqual(layer_index, 2)
            self.assertIsNotNone(doc.Layers[layer_index].Color)
            found = [o for o in doc.Objects if o.Attributes.LayerIndex == layer_index]
            self.assertEqual(len(found), 1)
        finally:
            sys.modules.pop("System", None)
            sys.modules.pop("System.Drawing", None)

    def test_union_layer(self) -> None:
        doc = self.rhino.RhinoDoc.ActiveDoc
        backend = self.backend
        backend.create_box({"name": "B1", "size": [2, 2, 2], "location": [0, 0, 0], "layer": "WALL"}, False)
        backend.create_box({"name": "B2", "size": [2, 2, 2], "location": [1, 0, 0], "layer": "WALL"}, False)
        result = backend.union_layer({"layer": "WALL"}, False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["unioned"])
        self.assertEqual(result["result"]["before"], 2)
        self.assertEqual(result["result"]["after"], 1)
        # originals deleted, one unioned solid remains on the layer
        self.assertEqual(len(doc.Objects), 3 + 1)

    def test_union_layer_many_boxes(self) -> None:
        doc = self.rhino.RhinoDoc.ActiveDoc
        backend = self.backend
        for index in range(60):
            backend.create_box(
                {"name": "M%d" % index, "size": [1, 1, 1], "location": [index * 0.5, 0, 0], "layer": "WALL"},
                False,
            )
        result = backend.union_layer({"layer": "WALL"}, False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["before"], 60)
        self.assertEqual(result["result"]["after"], 1)
        self.assertEqual(len(doc.Objects), 3 + 1)

    def test_rollback_unknown(self) -> None:
        result = self.backend.rollback("rhino-unknown")
        self.assertFalse(result["ok"])

    def test_delete_object(self) -> None:
        doc = self.rhino.RhinoDoc.ActiveDoc
        backend = self.backend
        created = backend.create_box({"name": "DelMe", "size": [1, 1, 1], "location": [0, 0, 0]}, False)
        object_id = created["result"]["object_id"]
        preview = backend.delete_object({"object_id": object_id}, True)
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["result"]["would_delete"])
        result = backend.delete_object({"object_id": object_id}, False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["deleted"])
        self.assertEqual(len(doc.Objects), 3)
        missing = backend.delete_object({"object_id": object_id}, False)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error_code"], "not_found")

    def test_get_objects(self) -> None:
        backend = self.backend
        backend.create_box({"name": "B1", "size": [2, 2, 2], "location": [0, 0, 0], "layer": "Wall"}, False)
        backend.create_box({"name": "B2", "size": [2, 2, 2], "location": [1, 0, 0], "layer": "Wall"}, False)
        result = backend.get_objects({"layer": "Wall"}, False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["total_matching"], 2)
        self.assertEqual(len(result["result"]["objects"]), 2)
        for entry in result["result"]["objects"]:
            self.assertIn("id", entry)
            self.assertEqual(entry["layer"], "Wall")
            self.assertIn("name", entry)
            self.assertIn("type", entry)


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
