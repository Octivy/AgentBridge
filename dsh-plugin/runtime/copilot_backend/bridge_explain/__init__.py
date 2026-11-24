"""解释层（AgentBridge 中间调和方：连接 + 解释 + 补能力）。"""

from bridge_explain.explain import (
    READ_TOOLS,
    explain_scene,
    explain_snapshot,
    explain_tool_result,
)

__all__ = ["READ_TOOLS", "explain_snapshot", "explain_scene", "explain_tool_result"]
