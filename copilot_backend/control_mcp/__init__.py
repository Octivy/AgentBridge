"""控制面 MCP：配置中心自身作为 Agent 工具，让智能体搭桥、管理软件与 MCP 接入。"""

from control_mcp.server import CONTROL_INSTRUCTIONS, create_control_server
from control_mcp.service import ControlService

__all__ = ["CONTROL_INSTRUCTIONS", "ControlService", "create_control_server"]
