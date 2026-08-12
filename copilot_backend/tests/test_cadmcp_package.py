import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cadmcp.server import SERVER_INSTRUCTIONS, _mcp_tools, create_mcp_server
from cadmcp.tool_registry import list_product_tools, list_tools


class CadMcpPackageTests(unittest.TestCase):
    def test_standalone_server_exposes_only_product_tools(self) -> None:
        definitions = list_product_tools()
        exposed = _mcp_tools(definitions)

        self.assertGreaterEqual(len(exposed), 8)
        self.assertEqual({tool.name for tool in exposed}, {tool.tool_name for tool in definitions})
        self.assertNotIn("arch_create_wall", {tool.name for tool in exposed})
        self.assertNotIn("arch_place_opening", {tool.name for tool in exposed})
        self.assertEqual(len(list_tools()), len(definitions))
        self.assertEqual(create_mcp_server().name, "cadmcp")

    def test_write_tools_expose_preview_first_schema_and_metadata(self) -> None:
        tools = {tool.name: tool for tool in _mcp_tools(list_product_tools())}

        draw_line = tools["draw_line"]
        self.assertTrue(draw_line.inputSchema["properties"]["dry_run"]["default"])
        self.assertFalse(draw_line.annotations.readOnlyHint)
        self.assertIn("dry_run=true", SERVER_INSTRUCTIONS)
        self.assertIn("permission_token", draw_line.inputSchema["properties"])

        snapshot = tools["get_drawing_snapshot"]
        self.assertTrue(snapshot.annotations.readOnlyHint)
        self.assertNotIn("dry_run", snapshot.inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
