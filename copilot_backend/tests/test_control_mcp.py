import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from control_mcp.scaffold import scaffold_adapter  # noqa: E402
from control_mcp.service import ControlService  # noqa: E402
from delivery.service import DeliveryService  # noqa: E402
from delivery.store import DeliveryStore  # noqa: E402
from host_config.service import HostConfigService  # noqa: E402
from host_config.store import HostConfigStore  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControlMcpScaffoldTests(unittest.TestCase):
    def test_scaffold_generates_working_adapter(self) -> None:
        target = Path(tempfile.mkdtemp(prefix="ab-ctrl-")) / "rhino"
        result = scaffold_adapter("rhino", "Rhino", target_dir=target)
        self.assertTrue(target.is_dir())
        for name in ("host.py", "backend.py", "registration.py", "background_host.py", "README.md"):
            self.assertTrue((target / name).exists(), name)
        self.assertEqual(result["files"], sorted(result["files"]))

        backend = _load_module("rhino_backend", target / "backend.py")
        host = _load_module("rhino_host", target / "host.py")
        adapter = host.HostAdapter(
            host_id="rhino-main",
            host_kind="rhino",
            product="Rhino",
            product_version="1.0",
            tools=backend.TOOLS,
            snapshot_fn=backend.snapshot,
            execute_fn=backend.runner,
            rollback_fn=backend.rollback,
        )
        adapter.start()
        try:
            request = urllib.request.Request(
                adapter.endpoint + "/manifest",
                headers={"x-cadcopilot-token": adapter.token},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            self.assertEqual(manifest["host_kind"], "rhino")
            self.assertEqual(
                {tool["tool_name"] for tool in manifest["tools"]},
                {"rhino_summary", "rhino_create_thing"},
            )
        finally:
            adapter.stop()

    def test_control_service_tools(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-ctrl-"))
        store = HostConfigStore(path=root / "configs.json", repo_root=root)
        service = HostConfigService(store=store, registry_dir=root / "hosts")
        delivery = DeliveryService(store=DeliveryStore(path=root / "deliveries.json"))
        control = ControlService(host_service=service, delivery=delivery)

        names = [tool.name for tool in control.list_tools()]
        for expected in (
            "ab_list_software",
            "ab_add_host",
            "ab_update_host",
            "ab_remove_host",
            "ab_scaffold_adapter",
            "ab_register_with_codex",
            "ab_record_deliverable",
            "ab_set_handoff",
        ):
            self.assertIn(expected, names)

        result = control.execute_tool("ab_list_software", {})
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["result"], list)

        result = control.execute_tool(
            "ab_add_host",
            {
                "host_id": "demo",
                "name": "Demo",
                "host_kind": "demo",
                "product": "Demo",
                "command": "python",
                "args": ["-c", "pass"],
                "cwd": str(root),
            },
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["host_id"], "demo")

        result = control.execute_tool("ab_preview_mcp", {})
        self.assertTrue(result["ok"], result)
        servers = [entry["name"] for entry in result["result"]["servers"]]
        self.assertIn("agentbridge", servers)

        result = control.execute_tool("ab_remove_host", {"host_id": "demo"})
        self.assertTrue(result["ok"], result)

        result = control.execute_tool(
            "ab_record_deliverable",
            {"task_id": "t1", "name": "out.png", "path": r"C:\tmp\out.png", "kind": "screenshot"},
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["deliverable_count"], 1)

        result = control.execute_tool(
            "ab_set_handoff",
            {"task_id": "t1", "summary": "完成", "verification_steps": ["检查 out.png"]},
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["handoff"]["summary"], "完成")

        result = control.execute_tool("ab_list_deliveries", {})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"][0]["task_id"], "t1")

        result = control.execute_tool("ab_does_not_exist", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "unknown_tool")

    def test_control_run_task_async(self) -> None:
        import asyncio

        root = Path(tempfile.mkdtemp(prefix="ab-ctrl-"))
        store = HostConfigStore(path=root / "configs.json", repo_root=root)
        service = HostConfigService(store=store, registry_dir=root / "hosts")
        delivery = DeliveryService(store=DeliveryStore(path=root / "deliveries.json"))

        async def fake_runner(request):
            return {"task_id": "t-x", "final_text": "done", "stopped_reason": "completed", "executed_tools": []}

        control = ControlService(host_service=service, delivery=delivery, task_runner=fake_runner)
        result = asyncio.run(control.execute_async("ab_run_task", {"message": "做点事", "approval": "full"}))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["task_id"], "t-x")
        self.assertIn("ab_run_task", [t.name for t in control.list_tools()])


if __name__ == "__main__":
    unittest.main()
