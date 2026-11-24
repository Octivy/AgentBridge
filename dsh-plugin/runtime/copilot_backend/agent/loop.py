"""Native tool-calling agent loop.

The loop keeps a canonical message history and delegates protocol conversion
to an ``AgentProvider``. Write tools are gated by an optional confirmation
callback so the product policy (dry-run -> one-time authorization -> CAD
transaction -> handle verification -> rollback) stays in the caller.

Canonical message shapes:

- user: ``{"role": "user", "content": "..."}``
- assistant: ``{"role": "assistant", "content": "...", "tool_calls": [{"id", "name", "arguments"}]}``
- tool: ``{"role": "tool", "tool_call_id": "...", "content": "..."}``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from cadmcp.tool_registry import ToolDefinition

from agent.tools import provider_tools, tool_result_message


class AgentProvider(Protocol):
    """Provider adapter that speaks one native tool-calling protocol."""

    protocol: str

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a canonical assistant message with ``content`` and ``tool_calls``."""


ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[str]]
ConfirmWrite = Callable[[Dict[str, Any]], Awaitable[bool]]
StepListener = Callable[["AgentStep"], Awaitable[None]]


@dataclass
class ExecutedTool:
    name: str
    arguments: Dict[str, Any]
    ok: bool
    result_text: str
    error_code: str = ""


@dataclass
class AgentStep:
    index: int
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    executed_tools: List[ExecutedTool] = field(default_factory=list)
    blocked_write: Optional[Dict[str, Any]] = None


@dataclass
class AgentResult:
    final_text: str
    steps: List[AgentStep] = field(default_factory=list)
    executed_tools: List[ExecutedTool] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = "completed"
    pending_write: Optional[Dict[str, Any]] = None
    # Canonical message history after the run. Needed to resume a task that
    # stopped at ``needs_confirmation`` (the blocked write gets its tool result
    # appended before the loop continues).
    history: List[Dict[str, Any]] = field(default_factory=list)


class AgentLoop:
    """Run a model until it stops calling tools or the iteration budget is hit."""

    def __init__(
        self,
        *,
        provider: AgentProvider,
        tools: Sequence[ToolDefinition],
        execute_tool: ToolExecutor,
        confirm_write: Optional[ConfirmWrite] = None,
        max_iterations: int = 12,
        on_step: Optional[StepListener] = None,
    ) -> None:
        self._provider = provider
        self._tools = {tool.tool_name: tool for tool in tools}
        self._execute_tool = execute_tool
        self._confirm_write = confirm_write
        self._max_iterations = max(1, max_iterations)
        self._on_step = on_step

    async def run(self, messages: Sequence[Mapping[str, Any]]) -> AgentResult:
        history: List[Dict[str, Any]] = [dict(message) for message in messages]
        tools = provider_tools(self._provider.protocol, self._tools.values())
        steps: List[AgentStep] = []
        executed: List[ExecutedTool] = []

        for index in range(self._max_iterations):
            response = await self._provider.complete(history, tools)
            assistant_content = str(response.get("content") or "")
            tool_calls = [dict(call) for call in (response.get("tool_calls") or [])]
            history.append(
                {"role": "assistant", "content": assistant_content, "tool_calls": tool_calls}
            )

            if not tool_calls:
                return AgentResult(
                    final_text=assistant_content,
                    steps=steps,
                    executed_tools=executed,
                    iterations=len(steps),
                    stopped_reason="completed",
                    history=history,
                )

            step = AgentStep(index=index, content=assistant_content, tool_calls=tool_calls)
            blocked_write: Optional[Dict[str, Any]] = None
            for call in tool_calls:
                name = str(call.get("name") or "")
                arguments = dict(call.get("arguments") or {})
                call_id = str(call.get("id") or "")
                tool_definition = self._tools.get(name)

                if tool_definition is None:
                    result = ExecutedTool(
                        name=name,
                        arguments=arguments,
                        ok=False,
                        result_text=f"ERROR: unknown tool '{name}'.",
                        error_code="unknown_tool",
                    )
                    step.executed_tools.append(result)
                    executed.append(result)
                    history.append(
                        tool_result_message(
                            self._provider.protocol,
                            call_id,
                            result.result_text,
                            is_error=True,
                        )
                    )
                    continue

                if self._is_write(tool_definition) and self._confirm_write is not None:
                    if not await self._confirm_write(call):
                        blocked_write = dict(call)
                        step.blocked_write = blocked_write
                        break

                try:
                    result_text = await self._execute_tool(name, arguments)
                    result = ExecutedTool(
                        name=name,
                        arguments=arguments,
                        ok=True,
                        result_text=result_text,
                    )
                except Exception as exc:
                    result = ExecutedTool(
                        name=name,
                        arguments=arguments,
                        ok=False,
                        result_text=f"ERROR: {exc}",
                        error_code="execution_error",
                    )
                step.executed_tools.append(result)
                executed.append(result)
                history.append(
                    tool_result_message(
                        self._provider.protocol,
                        call_id,
                        result.result_text,
                        is_error=not result.ok,
                    )
                )

            steps.append(step)
            if self._on_step is not None:
                await self._on_step(step)

            if blocked_write is not None:
                return AgentResult(
                    final_text=assistant_content,
                    steps=steps,
                    executed_tools=executed,
                    iterations=len(steps),
                    stopped_reason="needs_confirmation",
                    pending_write=blocked_write,
                    history=history,
                )

        return AgentResult(
            final_text=steps[-1].content if steps else "",
            steps=steps,
            executed_tools=executed,
            iterations=len(steps),
            stopped_reason="max_iterations",
            history=history,
        )

    @staticmethod
    def _is_write(tool: ToolDefinition) -> bool:
        risk = (tool.risk_level or "").strip().lower()
        side_effect = (tool.side_effect_level or "").strip().lower()
        return risk != "read_only" or side_effect != "none"
