"""Tool definitions for the AgentBridge control-plane MCP server."""

from __future__ import annotations

from typing import Any, Dict, List

from mcp import types


def _tool(name: str, title: str, description: str, properties: Dict[str, Any], required: List[str] | None = None) -> types.Tool:
    return types.Tool(
        name=name,
        title=title,
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
            **({"required": required} if required else {}),
        },
        annotations=types.ToolAnnotations(title=title, readOnlyHint=name not in {
            "ab_add_host",
            "ab_update_host",
            "ab_remove_host",
            "ab_start_host",
            "ab_stop_host",
            "ab_register_with_codex",
            "ab_register_with_claude",
            "ab_scaffold_adapter",
        }),
    )


STR = {"type": "string"}
BOOL = {"type": "boolean"}
STR_LIST = {"type": "array", "items": {"type": "string"}}


def control_tools() -> List[types.Tool]:
    return [
        _tool(
            "ab_list_software",
            "列出软件桥",
            "列出配置中心管理的所有软件桥及其实时状态（注册、健康、进程）。",
            {},
        ),
        _tool(
            "ab_software_status",
            "查询软件桥状态",
            "查询单个软件桥的实时状态。",
            {"host_id": STR},
            ["host_id"],
        ),
        _tool(
            "ab_test_connection",
            "测试软件桥连接",
            "测试某个软件桥的连接（健康检查）。",
            {"host_id": STR},
            ["host_id"],
        ),
        _tool(
            "ab_start_host",
            "启动软件桥",
            "启动某个软件桥的 MCP 服务进程。",
            {"host_id": STR},
            ["host_id"],
        ),
        _tool(
            "ab_stop_host",
            "停止软件桥",
            "停止某个软件桥的 MCP 服务进程。",
            {"host_id": STR},
            ["host_id"],
        ),
        _tool(
            "ab_add_host",
            "新增软件桥",
            "新增一个软件桥配置（软件名、类型、启动命令等）。",
            {
                "host_id": STR,
                "name": STR,
                "host_kind": STR,
                "product": STR,
                "command": STR,
                "args": STR_LIST,
                "cwd": STR,
                "env_vars": STR_LIST,
                "auto_start": BOOL,
            },
            ["host_id", "name", "host_kind"],
        ),
        _tool(
            "ab_update_host",
            "更新软件桥",
            "更新软件桥配置的任意字段。",
            {
                "host_id": STR,
                "name": STR,
                "host_kind": STR,
                "product": STR,
                "enabled": BOOL,
                "auto_start": BOOL,
                "command": STR,
                "args": STR_LIST,
                "cwd": STR,
                "env_vars": STR_LIST,
                "notes": STR,
            },
            ["host_id"],
        ),
        _tool(
            "ab_remove_host",
            "删除软件桥",
            "删除软件桥配置（同时停止其进程）。",
            {"host_id": STR},
            ["host_id"],
        ),
        _tool(
            "ab_preview_mcp",
            "预览 MCP 配置",
            "预览将写给 Codex / Claude 的 MCP 接入配置。",
            {},
        ),
        _tool(
            "ab_register_with_codex",
            "接入 Codex",
            "把生成的 MCP 服务器配置合并写入 ~/.codex/config.toml。",
            {},
        ),
        _tool(
            "ab_register_with_claude",
            "接入 Claude",
            "把生成的 MCP 服务器配置写入项目根目录 .mcp.json。",
            {},
        ),
        _tool(
            "ab_scaffold_adapter",
            "生成软件适配器脚手架",
            "为没有 MCP 的软件生成 Host Adapter 脚手架（host.py/backend.py/registration.py/README），"
            "让 Agent 或用户补全业务工具后即可接入。",
            {
                "host_kind": STR,
                "product": STR,
                "target_dir": STR,
            },
            ["host_kind", "product"],
        ),
        _tool(
            "ab_list_deliveries",
            "列出任务交付",
            "列出已登记交付物与交接总结的任务。",
            {},
        ),
        _tool(
            "ab_record_deliverable",
            "登记交付物",
            "为任务登记一个交付物（文件/截图/报告/模型等）。",
            {
                "task_id": STR,
                "name": STR,
                "path": STR,
                "kind": STR,
                "description": STR,
            },
            ["task_id", "name", "path"],
        ),
        _tool(
            "ab_set_handoff",
            "写交接总结",
            "为任务写入交接总结（做了什么、如何验证、下一步）。",
            {
                "task_id": STR,
                "summary": STR,
                "verification_steps": STR_LIST,
                "next_steps": STR_LIST,
            },
            ["task_id", "summary"],
        ),
        _tool(
            "ab_run_task",
            "运行 Agent 任务",
            "让 Agent 按用户需求拆解步骤，用宿主工具（hostmcp/cadmcp）自动执行并记录交付。"
            "approval=full 时写工具自动批准（dry-run 预览后自动提交）。",
            {
                "message": STR,
                "approval": STR,
                "provider": STR,
                "model": STR,
                "api_key": STR,
                "api_base_url": STR,
                "protocol": STR,
                "max_iterations": {"type": "integer", "minimum": 1, "maximum": 50},
                "tool_scope": STR,
            },
            ["message"],
        ),
    ]


__all__ = ["control_tools"]
