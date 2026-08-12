import unittest

from cadmcp.tool_registry import get_tool, list_product_tools, list_tools


EXPECTED_TOOLS = {
    "cad_health_check",
    "get_drawing_snapshot",
    "list_layers",
    "ensure_layer",
    "draw_line",
    "execute_draw_batch",
    "cad_rollback_transaction",
    "arch_get_drawing_context",
    "arch_recognize_functional_objects",
    "arch_extract_outer_outline",
    "arch_draw_outer_outline",
    "arch_suggest_layer_mapping",
    "arch_apply_layer_mapping",
}


class ProductToolRegistryTests(unittest.TestCase):
    def test_registry_contains_only_the_product_surface(self) -> None:
        self.assertEqual({tool.tool_name for tool in list_tools()}, EXPECTED_TOOLS)
        self.assertEqual({tool.tool_name for tool in list_product_tools()}, EXPECTED_TOOLS)

    def test_only_two_professional_skill_writes_are_reversible(self) -> None:
        for name in ("arch_draw_outer_outline", "arch_apply_layer_mapping"):
            tool = get_tool(name)
            self.assertTrue(tool.dry_run_supported)
            self.assertTrue(tool.rollback_supported)
            self.assertEqual(tool.risk_level, "reversible_write")

    def test_removed_authoring_tools_are_not_registered(self) -> None:
        for name in ("arch_create_wall", "arch_place_opening", "arch_create_room"):
            self.assertIsNone(get_tool(name))


if __name__ == "__main__":
    unittest.main()
