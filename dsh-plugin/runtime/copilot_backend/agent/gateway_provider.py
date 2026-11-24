"""AgentProvider implemented on the gateway's configured model settings.

The generic gateway ``call_provider`` is text-only; this adapter speaks the
three native tool-calling protocols directly so the AgentLoop can drive
host tools with a configured provider (DeepSeek / OpenAI / Anthropic / Ollama
compatible endpoints).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import httpx

from agent.loop import AgentProvider
from agent.tools import (
    parse_tool_calls,
    to_anthropic_messages,
    to_chat_messages,
    to_responses_input,
)
from gateway.provider_client import ModelProviderSettings
from shared.settings import SERVICE_TIMEOUT_SECONDS


class GatewayAgentProvider(AgentProvider):
    """Native tool-calling provider using the gateway's model settings."""

    def __init__(
        self,
        settings: ModelProviderSettings,
        system_prompt: str = "",
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._settings = settings
        self._system_prompt = system_prompt
        self._transport = transport
        self.protocol = settings.protocol
        self.label = f"{settings.display_name}/{settings.model}"

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if self._settings.requires_api_key and not self._settings.api_key.strip():
            raise ValueError(f"{self._settings.display_name} API Key 未配置")
        if not self._settings.api_base_url.strip():
            raise ValueError(f"{self._settings.display_name} API 地址未配置")
        if not self._settings.model.strip():
            raise ValueError(f"{self._settings.display_name} 模型名称未配置")
        async with httpx.AsyncClient(transport=self._transport, timeout=SERVICE_TIMEOUT_SECONDS) as client:
            protocol = (self.protocol or "openai_chat").strip().lower()
            if protocol == "anthropic_messages":
                return await self._complete_anthropic(client, messages, tools)
            if protocol == "openai_responses":
                return await self._complete_responses(client, messages, tools)
            return await self._complete_chat(client, messages, tools)

    def _headers(self, extra: Dict[str, str] | None = None) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        return self._settings.api_base_url.rstrip("/") + path

    async def _complete_chat(
        self,
        client: httpx.AsyncClient,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self._settings.model,
            "messages": to_chat_messages(messages),
        }
        if tools:
            payload["tools"] = list(tools)
        response = await client.post(self._url("/chat/completions"), json=payload, headers=self._headers())
        response.raise_for_status()
        data = response.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        return {
            "content": str(message.get("content") or ""),
            "tool_calls": parse_tool_calls("openai_chat", message),
        }

    async def _complete_responses(
        self,
        client: httpx.AsyncClient,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self._settings.model,
            "input": to_responses_input(messages),
        }
        if tools:
            payload["tools"] = list(tools)
        response = await client.post(self._url("/responses"), json=payload, headers=self._headers())
        response.raise_for_status()
        data = response.json()
        output = data.get("output") or []
        text = "".join(
            part.get("text") or ""
            for item in output
            if isinstance(item, Mapping) and item.get("type") == "message"
            for part in (item.get("content") or [])
            if isinstance(part, Mapping) and part.get("type") == "output_text"
        )
        assistant = {"output": output, "content": text}
        return {
            "content": text,
            "tool_calls": parse_tool_calls("openai_responses", assistant),
        }

    async def _complete_anthropic(
        self,
        client: httpx.AsyncClient,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": 2048,
            "system": self._system_prompt or "",
            "messages": to_anthropic_messages(messages),
        }
        if tools:
            payload["tools"] = list(tools)
        response = await client.post(
            self._url("/messages"),
            json=payload,
            headers=self._headers(
                {
                    "x-api-key": self._settings.api_key,
                    "anthropic-version": "2023-06-01",
                }
            ),
        )
        response.raise_for_status()
        data = response.json()
        blocks = data.get("content") or []
        text = "".join(block.get("text") or "" for block in blocks if isinstance(block, Mapping) and block.get("type") == "text")
        return {
            "content": text,
            "tool_calls": parse_tool_calls("anthropic_messages", {"content": blocks}),
        }


__all__ = ["GatewayAgentProvider"]
