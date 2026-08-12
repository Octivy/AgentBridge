import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from host_config.models import HostConfigCreate, HostConfigUpdate, LaunchSpec  # noqa: E402
from host_config.service import HostConfigService  # noqa: E402
from host_config.store import HostConfigStore  # noqa: E402


class HostConfigStoreTests(unittest.TestCase):
    def test_store_seeds_defaults_and_persists(self) -> None:
        root = Path(self._tmpdir())
        store = HostConfigStore(path=root / "configs.json", repo_root=root)
        configs = store.list()
        self.assertTrue(any(item.host_id == "autocad" for item in configs))
        self.assertTrue(any(item.host_id == "blender" for item in configs))

        store.upsert(configs[0].model_copy(update={"notes": "updated"}))
        reloaded = HostConfigStore(path=root / "configs.json")
        self.assertEqual(reloaded.get(configs[0].host_id).notes, "updated")

    def test_create_update_delete(self) -> None:
        root = Path(self._tmpdir())
        store = HostConfigStore(path=root / "configs.json", repo_root=root)
        service = HostConfigService(store=store, registry_dir=root / "hosts")

        created = service.create_config(
            HostConfigCreate(
                host_id="testhost",
                name="Test Host",
                host_kind="test",
                product="Test",
                launch=LaunchSpec(command="python", args=["-c", "pass"], cwd=str(root)),
            )
        )
        self.assertEqual(created.host_id, "testhost")
        self.assertIsNotNone(service.get_config("testhost"))

        updated = service.update_config("testhost", HostConfigUpdate(enabled=False))
        self.assertFalse(updated.enabled)
        self.assertTrue(service.delete_config("testhost"))
        self.assertIsNone(service.get_config("testhost"))

    def test_start_stop_manages_process(self) -> None:
        root = Path(self._tmpdir())
        store = HostConfigStore(path=root / "configs.json", repo_root=root)
        service = HostConfigService(store=store, registry_dir=root / "hosts")
        service.create_config(
            HostConfigCreate(
                host_id="sleeper",
                name="Sleeper",
                host_kind="sleeper",
                product="Sleeper",
                launch=LaunchSpec(command=sys.executable, args=["-c", "import time; time.sleep(60)"], cwd=str(root)),
            )
        )
        try:
            status = service.start("sleeper")
            self.assertTrue(status.process_running)
            self.assertIsNotNone(status.pid)
            status = service.stop("sleeper")
            self.assertFalse(status.process_running)
        finally:
            service.stop("sleeper")

    @staticmethod
    def _tmpdir() -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="agentbridge-hostconfig-")


if __name__ == "__main__":
    unittest.main()
