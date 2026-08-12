import json
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.provider_adapters import (
    AnthropicMessagesAdapter,
    OpenAIChatCompletionsAdapter,
    OpenAIResponsesAdapter,
    ProviderInvocation,
    negotiate_capabilities,
)


def _invocation() -> ProviderInvocation:
    return ProviderInvocation(
        display_name="Test",
        api_key="secret",
        api_base_url="https://model.example/v1",
        model="test-model",
        system_prompt="system",
        user_message="hello",
    )


class ProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_responses_adapter(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/responses")
            payload = json.loads(request.content)
            self.assertEqual(payload["instructions"], "system")
            self.assertEqual(payload["input"], "hello")
            return httpx.Response(200, json={"output_text": "response text"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OpenAIResponsesAdapter().generate(client, _invocation())

        self.assertEqual(result, "response text")

    async def test_openai_compatible_chat_adapter(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            return httpx.Response(200, json={"choices": [{"message": {"content": "chat text"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OpenAIChatCompletionsAdapter().generate(client, _invocation())

        self.assertEqual(result, "chat text")

    async def test_anthropic_messages_adapter(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/messages")
            self.assertEqual(request.headers["x-api-key"], "secret")
            return httpx.Response(200, json={"content": [{"type": "text", "text": "claude text"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await AnthropicMessagesAdapter().generate(client, _invocation())

        self.assertEqual(result, "claude text")

    async def test_openai_chat_serializes_vision_schema_and_tools(self) -> None:
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        tools = ({"type": "function", "function": {"name": "lookup", "parameters": schema}},)

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            content = payload["messages"][1]["content"]
            self.assertEqual(content[0], {"type": "text", "text": "hello"})
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertEqual(payload["response_format"]["json_schema"]["schema"], schema)
            self.assertEqual(payload["tools"], list(tools))
            return httpx.Response(200, json={"choices": [{"message": {"content": "structured"}}]})

        invocation = ProviderInvocation(**{**_invocation().__dict__, "image_base64": "YWJj", "response_schema": schema, "tools": tools})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OpenAIChatCompletionsAdapter().generate(client, invocation)

        self.assertEqual(result, "structured")

    async def test_openai_responses_streaming_contract(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertTrue(payload["stream"])
            body = (
                'data: {"type":"response.output_text.delta","delta":"stream "}\n\n'
                'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

        invocation = ProviderInvocation(**{**_invocation().__dict__, "stream": True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OpenAIResponsesAdapter().generate(client, invocation)

        self.assertEqual(result, "stream ok")

    async def test_anthropic_serializes_image_and_returns_tool_use(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            source = payload["messages"][0]["content"][0]["source"]
            self.assertEqual(source["media_type"], "image/jpeg")
            self.assertEqual(source["data"], "YWJj")
            self.assertEqual(payload["tools"][0]["name"], "inspect_drawing")
            return httpx.Response(
                200,
                json={"content": [{"type": "tool_use", "id": "call-1", "name": "inspect_drawing", "input": {}}]},
            )

        invocation = ProviderInvocation(
            **{
                **_invocation().__dict__,
                "image_base64": "data:image/jpeg;base64,YWJj",
                "tools": ({"name": "inspect_drawing", "input_schema": {"type": "object"}},),
            }
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await AnthropicMessagesAdapter().generate(client, invocation)

        self.assertEqual(json.loads(result)["tool_calls"][0]["name"], "inspect_drawing")

    def test_capability_negotiation_rejects_unsupported_structured_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "structured_output"):
            negotiate_capabilities(
                AnthropicMessagesAdapter(),
                image_requested=False,
                structured_output_requested=True,
                streaming_requested=False,
                tool_calling_requested=False,
            )


if __name__ == "__main__":
    unittest.main()
