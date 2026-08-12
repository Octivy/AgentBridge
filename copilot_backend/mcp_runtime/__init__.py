"""Backward-compatible imports for the standalone cadmcp package."""

from cadmcp.result_protocol import STANDARD_TOOL_RESULT_SCHEMA, build_tool_error_result, normalize_tool_result
from cadmcp.tool_executor import CadToolExecutor, cad_tool_executor

__all__ = [
    "CadToolExecutor",
    "STANDARD_TOOL_RESULT_SCHEMA",
    "build_tool_error_result",
    "cad_tool_executor",
    "normalize_tool_result",
]
