import json
import sys
from typing import Any, Dict, List
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.loop import AgentLoop
from agent.tools import (
    parse_tool_calls,
    provider_tools,
    to_anthropic_messages,
    to_chat_messages,
    to_responses_input,
    tool_result_message,
)
from cadmcp.tool_registry import get_product_tool


def _tool(name: str):
    tool = get_product_tool(name)
    assert tool is not None, f"missing product tool: {name}"
    return tool


class FakeProvider:
    protocol = "openai_chat"

    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.history_seen: List[List[Dict[str, Any]]] = []
        self.tools_seen: List[List[Dict[str, Any]]] = []

    async def complete(self, messages, tools):
        self.history_seen.append(list(messages))
        self.tools_seen.append(tools)
        return self._responses.pop(0)


class TestProtocolConverters:
    def test_chat_tool_schema(self):
        tools = provider_tools("openai_chat", [_tool("list_layers")])
        assert tools == [
            {
                "type": "function",
                "function": {
                    "name": "list_layers",
                    "description": tools[0]["function"]["description"],
                    "parameters": tools[0]["function"]["parameters"],
                },
            }
        ]
        assert tools[0]["function"]["name"] == "list_layers"

    def test_responses_tool_schema_has_no_function_wrapper(self):
        tools = provider_tools("openai_responses", [_tool("list_layers")])
        assert tools[0]["type"] == "function"
        assert tools[0]["name"] == "list_layers"
        assert "function" not in tools[0]

    def test_anthropic_tool_schema(self):
        tools = provider_tools("anthropic_messages", [_tool("list_layers")])
        assert tools[0] == {
            "name": "list_layers",
            "description": tools[0]["description"],
            "input_schema": tools[0]["input_schema"],
        }

    def test_parse_chat_tool_calls(self):
        native = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "list_layers", "arguments": "{}"},
                }
            ],
        }
        assert parse_tool_calls("openai_chat", native) == [
            {"id": "call_1", "name": "list_layers", "arguments": {}}
        ]

    def test_parse_responses_tool_calls(self):
        native = {
            "role": "assistant",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "fc_1",
                    "name": "draw_line",
                    "arguments": {"start": [0, 0], "end": [100, 0]},
                }
            ],
        }
        assert parse_tool_calls("openai_responses", native) == [
            {"id": "fc_1", "name": "draw_line", "arguments": {"start": [0, 0], "end": [100, 0]}}
        ]

    def test_parse_anthropic_tool_calls(self):
        native = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "checking layers"},
                {"type": "tool_use", "id": "tu_1", "name": "list_layers", "input": {}},
            ],
        }
        assert parse_tool_calls("anthropic_messages", native) == [
            {"id": "tu_1", "name": "list_layers", "arguments": {}}
        ]

    def test_tool_result_message_shapes(self):
        chat = tool_result_message("openai_chat", "call_1", "ok")
        assert chat == {"role": "tool", "tool_call_id": "call_1", "content": "ok"}
        responses = tool_result_message("openai_responses", "fc_1", "ok")
        assert responses == {"type": "function_call_output", "call_id": "fc_1", "output": "ok"}
        anthropic = tool_result_message("anthropic_messages", "tu_1", "boom", is_error=True)
        assert anthropic["content"] == [
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "boom", "is_error": True}
        ]

    def test_chat_history_conversion(self):
        canonical = [
            {"role": "user", "content": "draw a line"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [{"id": "c1", "name": "draw_line", "arguments": {"start": [0, 0], "end": [1, 1]}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "done"},
        ]
        converted = to_chat_messages(canonical)
        assert converted[0] == {"role": "user", "content": "draw a line"}
        assert converted[1]["tool_calls"][0]["function"]["name"] == "draw_line"
        assert json.loads(converted[1]["tool_calls"][0]["function"]["arguments"]) == {
            "start": [0, 0],
            "end": [1, 1],
        }
        assert converted[2] == {"role": "tool", "tool_call_id": "c1", "content": "done"}

    def test_anthropic_history_conversion(self):
        canonical = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [{"id": "tu_1", "name": "list_layers", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "tu_1", "content": "done"},
        ]
        converted = to_anthropic_messages(canonical)
        assert converted[0] == {"role": "user", "content": "hi"}
        assert converted[1]["content"][1] == {
            "type": "tool_use",
            "id": "tu_1",
            "name": "list_layers",
            "input": {},
        }
        assert converted[2]["content"][0]["type"] == "tool_result"

    def test_responses_history_conversion(self):
        canonical = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [{"id": "fc_1", "name": "list_layers", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "fc_1", "content": "done"},
        ]
        converted = to_responses_input(canonical)
        assert converted[1] == {"role": "assistant", "content": "ok"}
        assert converted[2] == {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "fc_1",
            "name": "list_layers",
            "arguments": "{}",
        }
        assert converted[3] == {"type": "function_call_output", "call_id": "fc_1", "output": "done"}


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_completes_after_tool_execution(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": "reading layers",
                    "tool_calls": [{"id": "c1", "name": "list_layers", "arguments": {}}],
                },
                {"role": "assistant", "content": "done", "tool_calls": []},
            ]
        )
        executed: List[str] = []

        async def execute(name, arguments):
            executed.append(name)
            return '{"layers": ["WALL"]}'

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("list_layers")],
            execute_tool=execute,
        )
        result = await loop.run([{"role": "user", "content": "read layers"}])
        assert result.stopped_reason == "completed"
        assert result.final_text == "done"
        assert executed == ["list_layers"]
        assert result.iterations == 1
        # the second provider call must include the tool result in history
        assert provider.history_seen[1][-1] == {
            "role": "tool",
            "tool_call_id": "c1",
            "content": '{"layers": ["WALL"]}',
        }

    @pytest.mark.asyncio
    async def test_write_tool_blocked_without_confirmation(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": "drawing",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "draw_line",
                            "arguments": {"start": [0, 0], "end": [100, 0]},
                        }
                    ],
                }
            ]
        )
        executed: List[str] = []

        async def execute(name, arguments):
            executed.append(name)
            return "ok"

        async def confirm(call):
            return False

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("draw_line")],
            execute_tool=execute,
            confirm_write=confirm,
        )
        result = await loop.run([{"role": "user", "content": "draw"}])
        assert result.stopped_reason == "needs_confirmation"
        assert result.pending_write == {
            "id": "c1",
            "name": "draw_line",
            "arguments": {"start": [0, 0], "end": [100, 0]},
        }
        assert executed == []

    @pytest.mark.asyncio
    async def test_write_tool_executes_after_confirmation(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": "drawing",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "draw_line",
                            "arguments": {"start": [0, 0], "end": [100, 0]},
                        }
                    ],
                },
                {"role": "assistant", "content": "line drawn", "tool_calls": []},
            ]
        )
        executed: List[str] = []

        async def execute(name, arguments):
            executed.append(name)
            return "ok"

        async def confirm(call):
            return True

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("draw_line")],
            execute_tool=execute,
            confirm_write=confirm,
        )
        result = await loop.run([{"role": "user", "content": "draw"}])
        assert result.stopped_reason == "completed"
        assert executed == ["draw_line"]

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_and_loop_recovers(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": "calling ghost",
                    "tool_calls": [{"id": "c1", "name": "ghost_tool", "arguments": {}}],
                },
                {
                    "role": "assistant",
                    "content": "retrying",
                    "tool_calls": [{"id": "c2", "name": "list_layers", "arguments": {}}],
                },
                {"role": "assistant", "content": "recovered", "tool_calls": []},
            ]
        )

        async def execute(name, arguments):
            return "ok"

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("list_layers")],
            execute_tool=execute,
        )
        result = await loop.run([{"role": "user", "content": "go"}])
        assert result.stopped_reason == "completed"
        assert result.final_text == "recovered"
        assert result.executed_tools[0].ok is False
        assert result.executed_tools[0].error_code == "unknown_tool"
        # the model must have seen the error in history before retrying
        assert provider.history_seen[1][-1]["role"] == "tool"
        assert "unknown tool" in provider.history_seen[1][-1]["content"]

    @pytest.mark.asyncio
    async def test_max_iterations_stops(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": f"step {index}",
                    "tool_calls": [{"id": f"c{index}", "name": "list_layers", "arguments": {}}],
                }
                for index in range(5)
            ]
        )

        async def execute(name, arguments):
            return "ok"

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("list_layers")],
            execute_tool=execute,
            max_iterations=3,
        )
        result = await loop.run([{"role": "user", "content": "go"}])
        assert result.stopped_reason == "max_iterations"
        assert result.iterations == 3
        assert len(result.executed_tools) == 3

    @pytest.mark.asyncio
    async def test_step_listener_is_called(self):
        provider = FakeProvider(
            [
                {
                    "role": "assistant",
                    "content": "reading",
                    "tool_calls": [{"id": "c1", "name": "list_layers", "arguments": {}}],
                },
                {"role": "assistant", "content": "done", "tool_calls": []},
            ]
        )
        steps_seen: List[int] = []

        async def execute(name, arguments):
            return "ok"

        async def on_step(step):
            steps_seen.append(step.index)

        loop = AgentLoop(
            provider=provider,
            tools=[_tool("list_layers")],
            execute_tool=execute,
            on_step=on_step,
        )
        result = await loop.run([{"role": "user", "content": "go"}])
        assert steps_seen == [0]
        assert result.stopped_reason == "completed"
