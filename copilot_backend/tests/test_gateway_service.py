import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.provider_client import ModelProviderSettings, resolve_provider_settings
from gateway.service import GatewayModelService, estimate_text_tokens
from shared.schemas import ChatMessageRequest


class GatewayModelServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_sanitized_multi_model_result(self):
        captured = {}

        async def provider(request, system_prompt, user_message):
            captured.update(request=request, system_prompt=system_prompt, user_message=user_message)
            return "  model response  "

        service = GatewayModelService(provider_caller=provider)
        request = ChatMessageRequest(message="inspect drawing", provider="openai", model="gpt-test")
        settings = ModelProviderSettings(provider="openai", display_name="OpenAI", api_base_url="https://example.test", api_key="key", model="gpt-test")
        with patch("gateway.service.resolve_provider_settings", return_value=settings):
            result = await service.request_text_result(request, "system", "user")

        self.assertEqual(result.text, "model response")
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-test")
        self.assertGreater(result.estimated_tokens, 0)
        self.assertEqual(captured["system_prompt"], "system")

    async def test_request_text_returns_only_text(self):
        async def provider(*_):
            return "ok"

        service = GatewayModelService(provider_caller=provider)
        request = ChatMessageRequest(message="hello")
        settings = ModelProviderSettings(provider="minimax", display_name="MiniMax", api_base_url="x", api_key="", model="m")
        with patch("gateway.service.resolve_provider_settings", return_value=settings):
            self.assertEqual(await service.request_text(request), "ok")

    def test_token_estimate_is_never_zero(self):
        self.assertEqual(estimate_text_tokens(""), 1)
        self.assertEqual(estimate_text_tokens("12345"), 2)

    def test_local_and_enterprise_compatible_models_allow_optional_api_key(self):
        for provider in ("openai_compatible", "enterprise_private"):
            settings = resolve_provider_settings(
                ChatMessageRequest(
                    message="查询规范",
                    provider=provider,
                    model="company-model",
                    api_base_url="http://127.0.0.1:9000/v1",
                )
            )
            self.assertFalse(settings.requires_api_key)
            self.assertEqual(settings.api_key, "")


if __name__ == "__main__":
    unittest.main()
