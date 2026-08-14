"""Tests for the unified connect chain, software detection and stale cleanup."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from host_config import connect as connect_module  # noqa: E402
from host_config.connect import (  # noqa: E402
    HostConnector,
    cleanup_stale_registrations,
    default_bridge_launch,
)
from host_config.detect import detect_installed_software  # noqa: E402
from host_config.models import HostConfigCreate, LaunchSpec  # noqa: E402
from host_config.service import HostConfigService  # noqa: E402
from host_config.store import HostConfigStore  # noqa: E402
from host_runtime.registry import HostRegistration, write_registration  # noqa: E402


def _service(root: Path) -> HostConfigService:
    store = HostConfigStore(path=root / "configs.json", repo_root=root)
    return HostConfigService(store=store, registry_dir=root / "hosts")


def _registration(host_id: str = "blender-main", host_kind: str = "blender", pid: int = 999999) -> HostRegistration:
    return HostRegistration(
        host_id=host_id,
        host_kind=host_kind,
        product="Blender",
        product_version="5.1",
        protocol_version="1",
        endpoint="http://127.0.0.1:9100",
        token="t",
        pid=pid,
        registered_at="2026-08-13T00:00:00+00:00",
    )


class DetectTests(unittest.TestCase):
    def test_detect_returns_all_supported_kinds_and_never_raises(self) -> None:
        results = detect_installed_software(adapter_status={"blender": {"installed": True}})
        kinds = {item["host_kind"] for item in results}
        self.assertEqual(kinds, {"blender", "sketchup", "rhino", "autocad"})
        blender = next(item for item in results if item["host_kind"] == "blender")
        self.assertTrue(blender["adapter_installed"])

    def test_detect_merges_adapter_status_default_false(self) -> None:
        results = detect_installed_software()
        for item in results:
            self.assertIn("detected", item)
            self.assertIs(item["adapter_installed"], False)


class ConnectFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "scripts").mkdir(parents=True, exist_ok=True)
        (self.root / "scripts" / "start-hostmcp.ps1").write_text("# stub", encoding="utf-8")
        self.service = _service(self.root)
        self.service.create_config(
            HostConfigCreate(
                host_id="blender-test",
                name="Blender",
                host_kind="blender",
                product="Blender",
                launch=LaunchSpec(command=sys.executable, args=["-c", "import time; time.sleep(60)"]),
            )
        )

    def tearDown(self) -> None:
        self.service.stop("blender-test")
        self._tmp.cleanup()

    def _connector(self, **kwargs) -> HostConnector:
        defaults = {
            "registry_dir": self.root / "hosts",
            "installers": {},
            "wait_seconds": 0.01,
            "poll_interval": 0.001,
            "sleep": lambda _: None,
        }
        defaults.update(kwargs)
        return HostConnector(self.service, **defaults)

    def test_connect_fails_early_when_software_not_detected(self) -> None:
        connector = self._connector()
        with mock.patch.object(connect_module, "detect_installed_software", return_value=[{"detected": False, "installations": []}]):
            result = connector.connect("blender-test")
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][0]["name"], "detect")
        self.assertFalse(result["steps"][0]["ok"])

    def test_connect_full_chain_persists_auto_start(self) -> None:
        detected = [{"detected": True, "installations": [{"version": "5.1"}], "adapter_installed": False}]
        registration = _registration(pid=os_getpid())
        write_registration(self.root / "hosts", registration)

        with (
            mock.patch.object(connect_module, "detect_installed_software", return_value=detected),
            mock.patch.object(connect_module, "HostClient") as client_cls,
        ):
            client_cls.return_value.health.return_value = {"ok": True}
            connector = self._connector(installers={"blender": lambda: {"ok": True, "message": "已安装"}})
            result = connector.connect("blender-test")

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False))
        self.assertTrue(result["persisted"])
        names = [step["name"] for step in result["steps"]]
        self.assertEqual(names, ["detect", "install_adapter", "start_bridge", "wait_registration", "health", "persist"])
        updated = self.service.get_config("blender-test")
        self.assertTrue(updated.enabled)
        self.assertTrue(updated.auto_start)

    def test_connect_skips_install_when_adapter_already_installed(self) -> None:
        detected = [{"detected": True, "installations": [{"version": "5.1"}], "adapter_installed": True}]
        write_registration(self.root / "hosts", _registration(pid=os_getpid()))
        installer_called = []

        def installer():
            installer_called.append(True)
            return {"ok": True, "message": "should not run"}

        with (
            mock.patch.object(connect_module, "detect_installed_software", return_value=detected),
            mock.patch.object(connect_module, "HostClient") as client_cls,
        ):
            client_cls.return_value.health.return_value = {"ok": True}
            connector = self._connector(installers={"blender": installer})
            result = connector.connect("blender-test")

        self.assertTrue(result["ok"])
        self.assertEqual(installer_called, [])
        install_step = next(step for step in result["steps"] if step["name"] == "install_adapter")
        self.assertTrue(install_step["ok"])
        self.assertIn("跳过", install_step["message"])

    def test_connect_times_out_waiting_registration_with_hint(self) -> None:
        detected = [{"detected": True, "installations": [{"version": "5.1"}], "adapter_installed": True}]
        with mock.patch.object(connect_module, "detect_installed_software", return_value=detected):
            connector = self._connector()
            result = connector.connect("blender-test")
        self.assertFalse(result["ok"])
        wait_step = next(step for step in result["steps"] if step["name"] == "wait_registration")
        self.assertFalse(wait_step["ok"])
        self.assertIn("自动连接", wait_step["detail"])
        self.assertIn("测试连接", wait_step["detail"])

    def test_default_bridge_launch_points_to_repo_script(self) -> None:
        launch = default_bridge_launch("blender")
        self.assertIn("start-hostmcp.ps1", launch["args"][-1])
        cad = default_bridge_launch("autocad")
        self.assertIn("start-cadmcp.ps1", cad["args"][-1])


class StaleCleanupTests(unittest.TestCase):
    def test_cleanup_removes_dead_pid_registrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_registration(directory, _registration(host_id="dead-host", pid=4_000_000))
            write_registration(directory, _registration(host_id="live-host", pid=os_getpid()))

            result = cleanup_stale_registrations(directory, probe_health=False)

            self.assertEqual(result["count"], 1)
            self.assertIn("dead-host", result["removed"][0])
            from host_runtime.registry import discover_hosts

            remaining = [item.host_id for item in discover_hosts(directory)]
            self.assertEqual(remaining, ["live-host"])

    def test_cleanup_removes_alive_pid_but_refusing_endpoint(self) -> None:
        """Rhino stays open but adapter not started: endpoint refuses (WinError 10061)."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # Current pid is alive, but 127.0.0.1:1 always refuses connections.
            zombie = _registration(host_id="zombie-rhino", pid=os_getpid())
            object.__setattr__(zombie, "endpoint", "http://127.0.0.1:1")
            write_registration(directory, zombie)

            result = cleanup_stale_registrations(directory, probe_timeout=0.5)

            self.assertEqual(result["count"], 1)
            from host_runtime.registry import discover_hosts

            self.assertEqual(discover_hosts(directory), [])

    def test_cleanup_keeps_healthy_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            registration = _registration(host_id="healthy-rhino", pid=os_getpid())
            write_registration(directory, registration)
            with mock.patch.object(connect_module, "HostClient") as client_cls:
                client_cls.return_value.health.return_value = {"ok": True}
                result = cleanup_stale_registrations(directory)
            self.assertEqual(result["count"], 0)


def os_getpid() -> int:
    import os

    return os.getpid()


if __name__ == "__main__":
    unittest.main()
