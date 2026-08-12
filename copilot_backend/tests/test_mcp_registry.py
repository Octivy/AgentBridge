import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from host_config.models import HostAdapterConfig, LaunchSpec  # noqa: E402
from host_config.store import HostConfigStore  # noqa: E402
from mcp_registry.service import (  # noqa: E402
    build_claude_json,
    build_mcp_servers,
    render_codex_toml,
    write_claude_config,
    write_codex_config,
)


def _store(root: Path) -> HostConfigStore:
    store = HostConfigStore(path=root / "configs.json", repo_root=root)
    store.upsert(
        HostAdapterConfig(
            host_id="autocad",
            name="AutoCAD",
            host_kind="autocad",
            product="AutoCAD",
            enabled=True,
            launch=LaunchSpec(
                command="powershell",
                args=["-m", "cadmcp"],
                cwd=str(root),
                env_vars=["CADMCP_BRIDGE_TOKEN"],
            ),
        )
    )
    store.upsert(
        HostAdapterConfig(
            host_id="blender",
            name="Blender",
            host_kind="blender",
            product="Blender",
            enabled=True,
            launch=LaunchSpec(
                command="python",
                args=["-m", "host_mcp"],
                cwd=str(root),
                env_vars=["HOSTMCP_REGISTRY_DIR"],
            ),
        )
    )
    return store


class McpRegistryTests(unittest.TestCase):
    def test_build_servers_derives_cadmcp_hostmcp_and_control(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-mcp-"))
        store = _store(root)
        entries = build_mcp_servers(store)
        names = [entry.name for entry in entries]
        self.assertEqual(sorted(names), ["agentbridge", "cadmcp", "hostmcp"])
        cadmcp = next(entry for entry in entries if entry.name == "cadmcp")
        self.assertEqual(cadmcp.command, "powershell")
        self.assertEqual(cadmcp.approval_mode, "approve")
        self.assertEqual(cadmcp.env_vars, ["CADMCP_BRIDGE_TOKEN"])
        control = next(entry for entry in entries if entry.name == "agentbridge")
        self.assertIn("control_mcp", control.args)

    def test_render_codex_toml_parses(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-mcp-"))
        entries = build_mcp_servers(_store(root))
        text = render_codex_toml(entries)
        data = tomllib.loads(text)
        self.assertIn("cadmcp", data["mcp_servers"])
        self.assertIn("hostmcp", data["mcp_servers"])
        self.assertIn("agentbridge", data["mcp_servers"])
        self.assertEqual(data["mcp_servers"]["cadmcp"]["default_tools_approval_mode"], "approve")

    def test_write_codex_config_merges_and_preserves(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-mcp-"))
        entries = build_mcp_servers(_store(root))
        target = root / "codex-config.toml"
        target.write_text('[desktop]\nsansFontSize = 14\n', encoding="utf-8")

        result = write_codex_config(entries, target=target)
        self.assertEqual(sorted(result["servers"]), ["agentbridge", "cadmcp", "hostmcp"])
        data = tomllib.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["desktop"]["sansFontSize"], 14)
        self.assertIn("cadmcp", data["mcp_servers"])
        self.assertIn("agentbridge", data["mcp_servers"])
        self.assertEqual(data["mcp_servers"]["hostmcp"]["cwd"], str(root))

    def test_write_claude_config_json(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-mcp-"))
        entries = build_mcp_servers(_store(root))
        target = root / ".mcp.json"
        result = write_claude_config(entries, target=target)
        self.assertTrue(target.exists())
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(set(data["mcpServers"]), {"agentbridge", "cadmcp", "hostmcp"})
        self.assertEqual(data["mcpServers"]["cadmcp"]["type"], "stdio")
        self.assertEqual(result["path"], str(target))

    def test_claude_json_shape(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ab-mcp-"))
        payload = build_claude_json(build_mcp_servers(_store(root)))
        self.assertIn("mcpServers", payload)


if __name__ == "__main__":
    unittest.main()
