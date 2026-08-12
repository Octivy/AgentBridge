"""Provider protocol adapters for native tool calling.

Supports the three protocols used by the gateway:
- ``openai_chat``: Chat Completions API.
- ``openai_responses``: Responses API.
- ``anthropic_messages``: Anthropic Messages API.

The agent loop keeps a canonical message history (see ``loop.py``) and this
module converts it to and from each provider's native wire format.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from cadmcp.tool_registry import ToolDefinition


def to_openai_chat_tools(tools: Iterable[ToolDefinition]) -> List[Dict[str, Any]]:
    """Chat Completions function tools."""

    return [
        {
            "type": "function",
            "function": {
                "name": tool.tool_name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def to_openai_responses_tools(tools: Iterable[ToolDefinition]) -> List[Dict[str, Any]]:
    """Responses API function tools (no ``function`` wrapper)."""

    return [
        {
            "type": "function",
            "name": tool.tool_name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
        for tool in tools
    ]


def to_anthropic_tools(tools: Iterable[ToolDefinition]) -> List[Dict[str, Any]]:
    """Anthropic Messages tools."""

    return [
        {
            "name": tool.tool_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]


def provider_tools(protocol: str, tools: Iterable[ToolDefinition]) -> List[Dict[str, Any]]:
    """Convert product tools to the provider-native tool schema."""

    normalized = (protocol or "openai_chat").strip().lower()
    if normalized == "anthropic_messages":
        return to_anthropic_tools(tools)
    if normalized == "openai_responses":
        return to_openai_responses_tools(tools)
    return to_openai_chat_tools(tools)


def parse_tool_calls(protocol: str, assistant_message: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract normalized tool calls from a provider assistant message.

    Normalized tool call shape: ``{"id": str, "name": str, "arguments": dict}``.
    """

    normalized = (protocol or "openai_chat").strip().lower()
    if normalized == "anthropic_messages":
        calls: List[Dict[str, Any]] = []
        for block in assistant_message.get("content") or []:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                calls.append(
                    {
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or ""),
                        "arguments": _normalize_arguments(block.get("input")),
                    }
                )
        return calls
    if normalized == "openai_responses":
        calls = []
        for item in assistant_message.get("output") or []:
            if isinstance(item, Mapping) and item.get("type") == "function_call":
                calls.append(
                    {
                        "id": str(item.get("call_id") or item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "arguments": _normalize_arguments(item.get("arguments")),
                    }
                )
        return calls
    calls = []
    for tool_call in assistant_message.get("tool_calls") or []:
        if isinstance(tool_call, Mapping):
            function = tool_call.get("function") or {}
            calls.append(
                {
                    "id": str(tool_call.get("id") or ""),
                    "name": str(function.get("name") or ""),
                    "arguments": _normalize_arguments(function.get("arguments")),
                }
            )
    return calls


def _normalize_arguments(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def tool_result_message(protocol: str, tool_call_id: str, content: str, *, is_error: bool = False) -> Dict[str, Any]:
    """Build the provider-native tool result message."""

    normalized = (protocol or "openai_chat").strip().lower()
    if normalized == "anthropic_messages":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content,
                    "is_error": bool(is_error),
                }
            ],
        }
    if normalized == "openai_responses":
        return {"type": "function_call_output", "call_id": tool_call_id, "output": content}
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def to_chat_messages(messages: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Convert canonical history to Chat Completions messages."""

    converted: List[Dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content") or ""
        if role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": str(message.get("tool_call_id") or ""),
                    "content": str(content),
                }
            )
        elif role == "assistant":
            assistant: Dict[str, Any] = {"role": "assistant", "content": str(content) if content else None}
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": str(call.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(call.get("name") or ""),
                            "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ]
            converted.append(assistant)
        else:
            converted.append({"role": "user", "content": str(content)})
    return converted


def to_anthropic_messages(messages: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Convert canonical history to Anthropic Messages."""

    converted: List[Dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content") or ""
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(message.get("tool_call_id") or ""),
                            "content": str(content),
                        }
                    ],
                }
            )
        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []
            if content:
                blocks.append({"type": "text", "text": str(content)})
            for call in message.get("tool_calls") or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(call.get("name") or ""),
                        "input": dict(call.get("arguments") or {}),
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
        else:
            converted.append({"role": "user", "content": str(content)})
    return converted


def to_responses_input(messages: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Convert canonical history to Responses API input items."""

    converted: List[Dict[str, Any]] = []
    for message in messages:
        if message.get("type") == "function_call_output":
            converted.append(dict(message))
            continue
        role = str(message.get("role") or "")
        content = message.get("content") or ""
        if role == "tool":
            converted.append(
                {
                    "type": "function_call_output",
                    "call_id": str(message.get("tool_call_id") or ""),
                    "output": str(content),
                }
            )
        elif role == "assistant":
            assistant_item: Dict[str, Any] = {"role": "assistant", "content": str(content) or ""}
            converted.append(assistant_item)
            for call in message.get("tool_calls") or []:
                converted.append(
                    {
                        "type": "function_call",
                        "id": str(call.get("id") or ""),
                        "call_id": str(call.get("id") or ""),
                        "name": str(call.get("name") or ""),
                        "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                    }
                )
        else:
            converted.append({"role": "user", "content": str(content)})
    return converted
