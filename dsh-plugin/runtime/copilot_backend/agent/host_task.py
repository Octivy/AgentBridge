"""Run an agent task against host tools (hostmcp) with a configured provider.

This is the product's "agent does the work" entry point: the model decomposes
the user requirement, calls host tools through the AgentLoop, write tools go
through dry-run -> one-time ticket -> apply (auto-approved in full mode), and
the outcome is recorded as a task delivery with a handoff summary.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agent.gateway_provider import GatewayAgentProvider
from agent.loop import AgentLoop, AgentStep, ConfirmWrite, ExecutedTool
from cadmcp.tool_executor import CadToolExecutor
from cadmcp.tool_registry import ToolDefinition, list_product_tools
from delivery.models import HandoffUpdate
from delivery.service import DeliveryService, delivery_service
from gateway.provider_client import resolve_provider_settings
from host_mcp.runtime import HostMcpExecutor
from shared.schemas import ChatMessageRequest


SYSTEM_PROMPT = (
    "You are AgentBridge, the bridge between AI agents and local software "
    "(AutoCAD, Blender, SketchUp, Rhino, ...). Decompose the user's requirement "
    "into concrete steps and use the provided host tools. Read tools return "
    "facts; write tools follow dry-run -> preview -> apply. After completing the "
    "work, summarize what was done, what changed, and how to verify it."
)


def build_skill_guidance(tool_names: List[str]) -> str:
    """Render enabled skills whose tools are available into agent guidance.

    Skills capture proven operating procedures (planner hints + auto reads) so
    the agent handles software the way accepted tasks did, instead of guessing.
    """

    from skills.registry import list_skills

    available = {name for name in tool_names}
    blocks: List[str] = []
    for skill in list_skills(enabled_only=True):
        relevant = [name for name in skill.mcp_tools if name in available]
        if not relevant:
            continue
        lines = [f"- Skill: {skill.name}（{skill.description}）"]
        for hint in skill.planner_hints:
            lines.append(f"  操作要点: {hint}")
        for call in skill.auto_tool_calls:
            if call.tool_name in available:
                lines.append(f"  起手动作: 先调用 {call.tool_name} 建立上下文")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return (
        "\n\n可用的操作 Skill（经过验收的操作规程，优先遵循）:\n" + "\n".join(blocks)
    )


class AgentTaskRequest(BaseModel):
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    protocol: Optional[str] = None
    approval: str = Field(default="full", description="full|execute|annotate")
    max_iterations: int = Field(default=12, ge=1, le=50)
    task_id: Optional[str] = None
    tool_scope: str = Field(default="hosts", description="hosts|cadmcp|all")


def host_tool_definitions(executor: HostMcpExecutor) -> List[ToolDefinition]:
    """Convert host_mcp tools (mcp types.Tool) to product ToolDefinitions."""

    definitions: List[ToolDefinition] = []
    for tool in executor.list_tools():
        annotations = tool.annotations
        read_only = bool(annotations and annotations.readOnlyHint)
        raw_meta = getattr(tool, "_meta", None)
        if raw_meta is None and hasattr(tool, "model_extra"):
            raw_meta = tool.model_extra or {}
        meta = dict(raw_meta or {})
        risk = "read_only" if read_only else "reversible_write"
        side_effect = "none" if read_only else str(meta.get("hostmcp/riskLevel") or "high")
        dry_run = bool(meta.get("hostmcp/dryRunSupported", not read_only))
        definitions.append(
            ToolDefinition(
                tool_name=tool.name,
                display_name=tool.title or tool.name,
                category=str(meta.get("hostmcp/category") or "host"),
                description=tool.description or "",
                input_schema=dict(tool.inputSchema or {}),
                dry_run_supported=dry_run,
                side_effect_level=side_effect,
                result_schema={},
                risk_level=risk,
                rollback_supported=True,
            )
        )
    return definitions


class HostToolExecutor:
    """Execute host tools through host_mcp, auto-approving write tickets in full mode."""

    def __init__(self, executor: HostMcpExecutor, approval: str = "full", trace_id: str = "") -> None:
        self._executor = executor
        self._auto_approve = approval in {"full", "execute"}
        self._trace_id = trace_id

    async def __call__(self, name: str, arguments: Dict[str, Any]) -> str:
        return await asyncio.to_thread(self._execute, name, arguments)

    def _execute(self, name: str, arguments: Dict[str, Any]) -> str:
        call = dict(arguments)
        call.setdefault("trace_id", self._trace_id)
        result = self._executor.execute_tool_sync(name, call)
        if (
            self._auto_approve
            and result.get("requires_permission")
            and result.get("permission_token")
        ):
            commit = dict(arguments)
            commit.update(
                {
                    "dry_run": False,
                    "permission_token": result["permission_token"],
                    "preview_hash": result.get("preview_hash") or "",
                }
            )
            commit.setdefault("trace_id", self._trace_id)
            result = self._executor.execute_tool_sync(name, commit)
        return json.dumps(result, ensure_ascii=False)


class CombinedToolExecutor:
    """Route tool calls to the host or CAD executor by tool scope."""

    def __init__(
        self,
        *,
        host_executor: Optional[HostMcpExecutor],
        cad_executor: Optional[CadToolExecutor],
        host_tools: List[ToolDefinition],
        cad_tools: List[ToolDefinition],
        approval: str = "full",
        trace_id: str = "",
    ) -> None:
        self._host = HostToolExecutor(host_executor, approval=approval, trace_id=trace_id) if host_executor else None
        self._cad = cad_executor
        self._host_names = {tool.tool_name for tool in host_tools}
        self._cad_names = {tool.tool_name for tool in cad_tools}
        self._cad_meta = {tool.tool_name: tool for tool in cad_tools}
        self._approval = approval
        self._trace_id = trace_id

    async def __call__(self, name: str, arguments: Dict[str, Any]) -> str:
        if name in self._cad_names:
            return await self._execute_cad(name, arguments)
        if name in self._host_names and self._host is not None:
            return await self._host(name, arguments)
        return json.dumps(
            {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {name}"},
            ensure_ascii=False,
        )

    async def _execute_cad(self, name: str, arguments: Dict[str, Any]) -> str:
        assert self._cad is not None
        call = dict(arguments)
        call.setdefault("trace_id", self._trace_id)
        tool = self._cad_meta.get(name)
        is_write = bool(tool and (tool.risk_level or "").strip().lower() != "read_only")
        dry_run = bool(call.pop("dry_run", is_write))
        result = await self._cad.execute_tool(name, call, caller="host_task", dry_run=dry_run)
        if (
            self._approval in {"full", "execute"}
            and result.get("requires_permission")
            and result.get("permission_token")
        ):
            commit = dict(call)
            commit.update(
                {
                    "permission_token": result["permission_token"],
                    "preview_hash": result.get("preview_hash") or "",
                }
            )
            result = await self._cad.execute_tool(name, commit, caller="host_task", dry_run=False)
        return json.dumps(result, ensure_ascii=False)


@dataclass
class TaskContext:
    """Resolved executors, tools and provider for one agent task run."""

    host_executor: Optional[HostMcpExecutor]
    cad_executor: Optional[CadToolExecutor]
    host_tools: List[ToolDefinition]
    cad_tools: List[ToolDefinition]
    tools: List[ToolDefinition]
    tool_executor: "CombinedToolExecutor"
    provider: Any
    protocol: str
    system_prompt: str


def build_task_context(
    request: AgentTaskRequest,
    *,
    executor: Optional[HostMcpExecutor] = None,
    cad_executor: Optional[CadToolExecutor] = None,
    cad_tools: Optional[List[ToolDefinition]] = None,
    provider: Optional[GatewayAgentProvider] = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> Optional[TaskContext]:
    """Resolve executors, tool definitions and the model provider.

    Returns ``None`` when no tools are available (caller short-circuits with
    the ``no_tools`` result).
    """

    scope = (request.tool_scope or "hosts").strip().lower()
    use_host = scope in {"hosts", "all"}
    use_cad = scope in {"cadmcp", "all"}

    host_executor = executor or (HostMcpExecutor() if use_host else None)
    host_tools = host_tool_definitions(host_executor) if host_executor else []
    cad_executor = cad_executor or (CadToolExecutor() if use_cad else None)
    cad_tool_defs = list(cad_tools) if cad_tools is not None else (list_product_tools() if use_cad else [])
    tools = host_tools + cad_tool_defs
    if not tools:
        return None

    guidance = build_skill_guidance([tool.tool_name for tool in tools])
    if guidance and not system_prompt.endswith(guidance):
        system_prompt = system_prompt + guidance

    if provider is None:
        provider_request = ChatMessageRequest(
            message=request.message,
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            api_base_url=request.api_base_url,
            protocol=request.protocol,
            mode="standard",
            capabilities=["tool_calling", "streaming"],
        )
        settings = resolve_provider_settings(provider_request)
        provider = GatewayAgentProvider(settings, system_prompt=system_prompt)

    tool_executor = CombinedToolExecutor(
        host_executor=host_executor,
        cad_executor=cad_executor,
        host_tools=host_tools,
        cad_tools=cad_tool_defs,
        approval=request.approval,
        trace_id=(request.task_id or "").strip(),
    )
    return TaskContext(
        host_executor=host_executor,
        cad_executor=cad_executor,
        host_tools=host_tools,
        cad_tools=cad_tool_defs,
        tools=tools,
        tool_executor=tool_executor,
        provider=provider,
        protocol=str(getattr(provider, "protocol", "openai_chat") or "openai_chat"),
        system_prompt=system_prompt,
    )


async def _auto_confirm(call: Dict[str, Any]) -> bool:
    del call
    return True


async def _block_confirm(call: Dict[str, Any]) -> bool:
    """Annotate mode: stop at the first write so the user can confirm it."""

    del call
    return False


def confirm_policy(approval: str) -> ConfirmWrite:
    """Map approval mode to the loop's write gate.

    ``full``/``execute`` auto-approve; anything else (``annotate``) blocks the
    write and surfaces it as ``pending_write`` so the panel can offer
    confirm/reject.
    """

    return _auto_confirm if approval in {"full", "execute"} else _block_confirm


def serialize_executed(item: ExecutedTool, result_limit: int = 0) -> Dict[str, Any]:
    text = item.result_text if result_limit <= 0 else item.result_text[:result_limit]
    return {
        "name": item.name,
        "ok": item.ok,
        "error_code": item.error_code,
        "result_text": text,
    }


def serialize_step(step: AgentStep, index: int, result_limit: int = 800) -> Dict[str, Any]:
    return {
        "index": index,
        "content": step.content,
        "tool_calls": step.tool_calls,
        "executed_tools": [serialize_executed(item, result_limit) for item in step.executed_tools],
        "blocked_write": step.blocked_write,
    }


def record_task_handoff(
    delivery: DeliveryService, task_id: str, user_goal: str, executed: List[Dict[str, Any]]
) -> None:
    delivery.set_handoff(
        task_id,
        HandoffUpdate(
            summary=f"Agent 任务完成：{user_goal[:200]}",
            verification_steps=[
                f"检查工具执行结果：{item['name']}（{'成功' if item['ok'] else '失败'}）" for item in executed
            ]
            or ["无工具调用"],
            next_steps=["由用户验收交付物"] if executed else [],
        ),
    )


async def run_host_task(
    request: AgentTaskRequest,
    *,
    executor: Optional[HostMcpExecutor] = None,
    cad_executor: Optional[CadToolExecutor] = None,
    cad_tools: Optional[List[ToolDefinition]] = None,
    delivery: Optional[DeliveryService] = None,
    provider: Optional[GatewayAgentProvider] = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """Run the agent loop against host tools and record the delivery.

    Synchronous (request/response) form used by the control-plane MCP. The
    panel uses ``agent.task_runner`` instead, which adds progress tracking and
    write confirmation on top of the same building blocks.
    """

    task_id = (request.task_id or "").strip() or str(uuid.uuid4())
    delivery = delivery or delivery_service
    request = request.model_copy(update={"task_id": task_id})

    context = build_task_context(
        request,
        executor=executor,
        cad_executor=cad_executor,
        cad_tools=cad_tools,
        provider=provider,
        system_prompt=system_prompt,
    )
    if context is None:
        return {
            "task_id": task_id,
            "final_text": "没有可用的宿主工具，请先在配置中心确认软件桥在线。",
            "stopped_reason": "no_tools",
            "steps": [],
            "executed_tools": [],
        }

    loop = AgentLoop(
        provider=context.provider,
        tools=context.tools,
        execute_tool=context.tool_executor,
        confirm_write=confirm_policy(request.approval),
        max_iterations=request.max_iterations,
    )
    result = await loop.run([{"role": "user", "content": request.message}])

    executed = [serialize_executed(item) for item in result.executed_tools]
    steps = [
        {
            "index": item.index,
            "content": item.content,
            "tool_calls": item.tool_calls,
            "blocked_write": item.blocked_write,
        }
        for item in result.steps
    ]

    record_task_handoff(delivery, task_id, request.message, executed)

    return {
        "task_id": task_id,
        "final_text": result.final_text,
        "stopped_reason": result.stopped_reason,
        "iterations": result.iterations,
        "steps": steps,
        "executed_tools": executed,
        "pending_write": result.pending_write,
    }


__all__ = [
    "AgentTaskRequest",
    "CombinedToolExecutor",
    "HostToolExecutor",
    "TaskContext",
    "build_task_context",
    "confirm_policy",
    "host_tool_definitions",
    "record_task_handoff",
    "run_host_task",
    "serialize_executed",
    "serialize_step",
]
