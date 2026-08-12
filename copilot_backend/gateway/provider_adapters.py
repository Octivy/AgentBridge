from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class ProviderInvocation:
    display_name: str
    api_key: str
    api_base_url: str
    model: str
    system_prompt: str
    user_message: str
    image_base64: str = ""
    response_schema: dict[str, Any] | None = None
    tools: tuple[dict[str, Any], ...] = ()
    stream: bool = False


@dataclass(frozen=True)
class ProviderCapabilities:
    vision: bool = False
    structured_output: bool = False
    streaming: bool = False
    tool_calling: bool = False

    def as_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, enabled in (
                ("vision", self.vision),
                ("structured_output", self.structured_output),
                ("streaming", self.streaming),
                ("tool_calling", self.tool_calling),
            )
            if enabled
        )


class ProviderResponseError(RuntimeError):
    def __init__(self, status_code: int, response_text: str) -> None:
        super().__init__(f"HTTP {status_code}: {response_text}")
        self.status_code = status_code
        self.response_text = response_text


class ProviderAdapter(Protocol):
    capabilities: ProviderCapabilities

    async def generate(self, client: httpx.AsyncClient, invocation: ProviderInvocation) -> str:
        ...


def _bearer_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = await client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        raise ProviderResponseError(response.status_code, response.text)
    try:
        body = response.json()
    except ValueError as exc:
        raise ValueError("模型服务返回了无效 JSON。") from exc
    if not isinstance(body, dict):
        raise ValueError("模型服务返回的 JSON 不是对象。")
    return body


async def _post_sse(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    delta_reader,
) -> str:
    parts: list[str] = []
    async with client.stream("POST", url, headers=headers, json=payload) as response:
        if response.status_code >= 400:
            body = (await response.aread()).decode("utf-8", errors="replace")
            raise ProviderResponseError(response.status_code, body)
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = delta_reader(event)
            if delta:
                parts.append(str(delta))
    return "".join(parts).strip()


def _image_data_url(value: str) -> str:
    image = str(value or "").strip()
    return image if image.startswith("data:") else "data:image/png;base64," + image


def _anthropic_image_source(value: str) -> dict[str, str]:
    image = str(value or "").strip()
    media_type = "image/png"
    data = image
    if image.startswith("data:") and ";base64," in image:
        header, data = image.split(";base64,", 1)
        media_type = header[5:] or media_type
    return {"type": "base64", "media_type": media_type, "data": data}


class OpenAIChatCompletionsAdapter:
    capabilities = ProviderCapabilities(True, True, True, True)

    async def generate(self, client: httpx.AsyncClient, invocation: ProviderInvocation) -> str:
        user_content: Any = invocation.user_message
        if invocation.image_base64:
            user_content = [
                {"type": "text", "text": invocation.user_message},
                {"type": "image_url", "image_url": {"url": _image_data_url(invocation.image_base64)}},
            ]
        payload: dict[str, Any] = {
            "model": invocation.model,
            "temperature": 0.2,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": invocation.system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if invocation.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "cad_response", "schema": invocation.response_schema, "strict": True},
            }
        if invocation.tools:
            payload["tools"] = list(invocation.tools)
        if invocation.stream:
            payload["stream"] = True
            return await _post_sse(
                client,
                invocation.api_base_url.rstrip("/") + "/chat/completions",
                headers=_bearer_headers(invocation.api_key),
                payload=payload,
                delta_reader=lambda event: (((event.get("choices") or [{}])[0].get("delta") or {}).get("content")),
            )
        body = await _post_json(
            client,
            invocation.api_base_url.rstrip("/") + "/chat/completions",
            headers=_bearer_headers(invocation.api_key),
            payload=payload,
        )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Chat Completions 响应缺少 choices[0].message。") from exc
        if content is None:
            tool_calls = body.get("choices", [{}])[0].get("message", {}).get("tool_calls")
            if tool_calls:
                return json.dumps({"tool_calls": tool_calls}, ensure_ascii=False)
            raise ValueError("Chat Completions 响应缺少 content 或 tool_calls。")
        if isinstance(content, list):
            parts = [
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "\n".join(part for part in parts if part).strip()
        return str(content or "").strip()


class OpenAIResponsesAdapter:
    capabilities = ProviderCapabilities(True, True, True, True)

    async def generate(self, client: httpx.AsyncClient, invocation: ProviderInvocation) -> str:
        input_value: Any = invocation.user_message
        if invocation.image_base64:
            input_value = [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": invocation.user_message},
                    {"type": "input_image", "image_url": _image_data_url(invocation.image_base64)},
                ],
            }]
        payload: dict[str, Any] = {
            "model": invocation.model,
            "instructions": invocation.system_prompt,
            "input": input_value,
            "max_output_tokens": 4096,
        }
        if invocation.response_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "cad_response",
                    "schema": invocation.response_schema,
                    "strict": True,
                }
            }
        if invocation.tools:
            payload["tools"] = list(invocation.tools)
        if invocation.stream:
            payload["stream"] = True
            return await _post_sse(
                client,
                invocation.api_base_url.rstrip("/") + "/responses",
                headers=_bearer_headers(invocation.api_key),
                payload=payload,
                delta_reader=lambda event: event.get("delta") if event.get("type") == "response.output_text.delta" else "",
            )
        body = await _post_json(
            client,
            invocation.api_base_url.rstrip("/") + "/responses",
            headers=_bearer_headers(invocation.api_key),
            payload=payload,
        )
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text = str(content.get("text") or "").strip()
                    if text:
                        parts.append(text)
        if not parts:
            tool_calls = [item for item in body.get("output") or [] if isinstance(item, dict) and item.get("type") == "function_call"]
            if tool_calls:
                return json.dumps({"tool_calls": tool_calls}, ensure_ascii=False)
            raise ValueError("Responses API 响应缺少 output_text。")
        return "\n".join(parts)


class AnthropicMessagesAdapter:
    capabilities = ProviderCapabilities(True, False, True, True)

    async def generate(self, client: httpx.AsyncClient, invocation: ProviderInvocation) -> str:
        user_content: Any = invocation.user_message
        if invocation.image_base64:
            user_content = [
                {"type": "image", "source": _anthropic_image_source(invocation.image_base64)},
                {"type": "text", "text": invocation.user_message},
            ]
        payload: dict[str, Any] = {
            "model": invocation.model,
            "max_tokens": 4096,
            "system": invocation.system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }
        if invocation.tools:
            payload["tools"] = list(invocation.tools)
        if invocation.stream:
            payload["stream"] = True
            return await _post_sse(
                client,
                invocation.api_base_url.rstrip("/") + "/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": invocation.api_key,
                    "anthropic-version": "2023-06-01",
                },
                payload=payload,
                delta_reader=lambda event: (event.get("delta") or {}).get("text") if event.get("type") == "content_block_delta" else "",
            )
        body = await _post_json(
            client,
            invocation.api_base_url.rstrip("/") + "/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": invocation.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
        )
        parts = [
            str(item.get("text") or "")
            for item in body.get("content") or []
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = "\n".join(part for part in parts if part).strip()
        if not text:
            tool_calls = [item for item in body.get("content") or [] if isinstance(item, dict) and item.get("type") == "tool_use"]
            if tool_calls:
                return json.dumps({"tool_calls": tool_calls}, ensure_ascii=False)
            raise ValueError("Anthropic Messages 响应缺少文本 content。")
        return text


_ADAPTERS: dict[str, ProviderAdapter] = {
    "openai_chat": OpenAIChatCompletionsAdapter(),
    "openai_responses": OpenAIResponsesAdapter(),
    "anthropic_messages": AnthropicMessagesAdapter(),
}


def get_provider_adapter(protocol: str) -> ProviderAdapter:
    try:
        return _ADAPTERS[protocol]
    except KeyError as exc:
        raise ValueError(f"不支持的模型协议: {protocol}") from exc


def negotiate_capabilities(
    adapter: ProviderAdapter,
    *,
    image_requested: bool,
    structured_output_requested: bool,
    streaming_requested: bool,
    tool_calling_requested: bool,
) -> None:
    requested = {
        "vision": image_requested,
        "structured_output": structured_output_requested,
        "streaming": streaming_requested,
        "tool_calling": tool_calling_requested,
    }
    unsupported = [name for name, enabled in requested.items() if enabled and not getattr(adapter.capabilities, name)]
    if unsupported:
        raise ValueError("模型协议不支持请求的能力: " + ", ".join(unsupported))


__all__ = [
    "AnthropicMessagesAdapter",
    "OpenAIChatCompletionsAdapter",
    "OpenAIResponsesAdapter",
    "ProviderInvocation",
    "ProviderCapabilities",
    "ProviderResponseError",
    "get_provider_adapter",
    "negotiate_capabilities",
]
