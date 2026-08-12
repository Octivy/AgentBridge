"""Standalone MCP tool service for AgentBridge."""

__version__ = "0.2.0"

from cadmcp.result_protocol import STANDARD_TOOL_RESULT_SCHEMA, build_tool_error_result, normalize_tool_result
from cadmcp.tool_executor import CadToolExecutor, cad_tool_executor
from cadmcp.tool_registry import ToolDefinition, get_tool, list_tools

__all__ = [
    "CadToolExecutor",
    "STANDARD_TOOL_RESULT_SCHEMA",
    "ToolDefinition",
    "build_tool_error_result",
    "cad_tool_executor",
    "get_tool",
    "list_tools",
    "normalize_tool_result",
    "__version__",
]
