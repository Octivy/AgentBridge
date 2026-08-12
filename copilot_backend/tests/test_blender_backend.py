"""Unit tests for the Blender backend using a fake ``bpy`` module."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FakeMesh:
    def __init__(self, name: str = "Mesh") -> None:
        self.name = name
        self.users = 1


class FakeObject:
    def __init__(self, name: str, location=(0.0, 0.0, 0.0), data=None) -> None:
        self._name = name
        self._data = data
        self.type = "MESH"
        self.location = [float(value) for value in location]
        self.scale = [1.0, 1.0, 1.0]
        self.data = FakeMesh(f"{name}Mesh")
        self.parent = None

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if self._data is not None:
            self._data.objects.pop(self._name, None)
            self._name = value
            self._data.objects[value] = self
            self._data._sync()
        else:
            self._name = value

    def visible_get(self) -> bool:
        return True


class FakeObjectsCollection(dict):
    def remove(self, obj, do_unlink: bool = False) -> None:
        self.pop(obj.name, None)


class FakeMeshesCollection(dict):
    def remove(self, mesh) -> None:
        self.pop(mesh.name, None)


class FakeData:
    def __init__(self) -> None:
        self.objects: FakeObjectsCollection = FakeObjectsCollection()
        self.meshes: FakeMeshesCollection = FakeMeshesCollection()
        self.scene_objects: list = []

    def _sync(self) -> None:
        self.scene_objects[:] = list(self.objects.values())

    def get(self, name: str):
        return self.objects.get(name)


class FakeOpsMesh:
    def __init__(self, context) -> None:
        self._context = context

    def _add(self, location, **kwargs):
        data = self._context.collection._data
        obj = FakeObject(f"Generated{len(self._context.scene.objects) + 1}", location, data=data)
        self._context.collection.objects_link(obj)
        self._context.object = obj
        return obj

    def primitive_cube_add(self, size=2.0, location=(0, 0, 0), **kwargs):
        return self._add(location)

    def primitive_uv_sphere_add(self, radius=1.0, location=(0, 0, 0), **kwargs):
        return self._add(location)

    def primitive_cylinder_add(self, radius=1.0, depth=2.0, location=(0, 0, 0), **kwargs):
        return self._add(location)

    def primitive_cone_add(self, radius1=1.0, radius2=0.0, depth=2.0, location=(0, 0, 0), **kwargs):
        return self._add(location)


class FakeOps:
    def __init__(self, context) -> None:
        self.mesh = FakeOpsMesh(context)


class FakeCollection:
    def __init__(self, data: FakeData) -> None:
        self._data = data

    def objects_link(self, obj) -> None:
        self._data.objects[obj.name] = obj
        self._data._sync()


class FakeSceneObjects(list):
    def __init__(self, data: FakeData) -> None:
        super().__init__()
        self._data = data


def _load_backend(fake_bpy):
    path = Path(__file__).resolve().parents[2] / "adapters" / "blender" / "backend.py"
    previous = sys.modules.pop("bpy", None)
    sys.modules["bpy"] = fake_bpy
    spec = importlib.util.spec_from_file_location("blender_backend_ut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if previous is None:
        sys.modules.pop("bpy", None)
    else:
        sys.modules["bpy"] = previous
    return module


def _make_bpy():
    data = FakeData()
    collection = FakeCollection(data)
    scene = SimpleNamespace(
        name="Scene",
        frame_current=1,
        objects=FakeSceneObjects(data),
        render=SimpleNamespace(
            resolution_x=1280,
            resolution_y=720,
            resolution_percentage=100,
            filepath="",
            engine="",
            film_transparent=False,
            image_settings=SimpleNamespace(file_format="PNG"),
        ),
    )
    context = SimpleNamespace(
        scene=scene,
        object=None,
        collection=collection,
        view_layer=SimpleNamespace(objects=SimpleNamespace(active=None)),
    )
    return SimpleNamespace(
        context=context,
        data=data,
        ops=FakeOps(context),
        types=SimpleNamespace(RenderSettings=SimpleNamespace(bl_rna=SimpleNamespace(properties={}))),
    )


class BlenderBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = _load_backend(_make_bpy())

    def test_create_primitive_dry_run_apply_rollback(self) -> None:
        backend = self.backend
        dry = backend.create_primitive({"kind": "sphere", "name": "Ball", "size": 1.0, "location": [1, 2, 3]}, True)
        self.assertTrue(dry["ok"])
        self.assertEqual(dry["result"]["preview"]["kind"], "sphere")

        applied = backend.create_primitive({"kind": "sphere", "name": "Ball", "size": 1.0, "location": [1, 2, 3]}, False)
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["rollback_token"], "blender-primitive-Ball")
        self.assertIsNotNone(backend.bpy.data.objects.get("Ball"))

        rolled = backend.rollback(applied["rollback_token"])
        self.assertTrue(rolled["ok"])
        self.assertTrue(rolled["result"]["rolled_back"])
        self.assertIsNone(backend.bpy.data.objects.get("Ball"))

    def test_create_primitive_invalid_kind(self) -> None:
        result = self.backend.create_primitive({"kind": "torus", "name": "X"}, True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")

    def test_move_object_preview_apply_rollback(self) -> None:
        backend = self.backend
        backend.bpy.data.objects["Cube"] = FakeObject("Cube", (0, 0, 0))
        backend.bpy.data._sync()

        dry = backend.move_object({"name": "Cube", "location": [5, 0, 0]}, True)
        self.assertTrue(dry["ok"])
        self.assertEqual(dry["result"]["preview"]["from"], [0.0, 0.0, 0.0])
        self.assertEqual(dry["result"]["preview"]["to"], [5.0, 0.0, 0.0])

        applied = backend.move_object({"name": "Cube", "location": [5, 0, 0]}, False)
        self.assertTrue(applied["ok"])
        self.assertEqual(backend.bpy.data.objects["Cube"].location, [5.0, 0.0, 0.0])

        rolled = backend.rollback(applied["rollback_token"])
        self.assertTrue(rolled["ok"])
        self.assertEqual(backend.bpy.data.objects["Cube"].location, [0.0, 0.0, 0.0])

    def test_move_object_missing(self) -> None:
        result = self.backend.move_object({"name": "Nope", "location": [1, 1, 1]}, True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "object_not_found")

    def test_rollback_unknown_token(self) -> None:
        result = self.backend.rollback("blender-unknown-token")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")

    def test_render_scene_dry_run_returns_preview(self) -> None:
        result = self.backend.render_scene(
            {"filepath": r"C:\tmp\out.png", "width": 256, "height": 144, "engine": "workbench"},
            True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["preview"]["filepath"].endswith("out.png"))
        self.assertEqual(result["result"]["preview"]["engine"], "workbench")


if __name__ == "__main__":
    unittest.main()
