import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product.model_config_service import ModelConfigService
from shared.schemas import AdminModelConfigUpdateRequest, AdminModelProviderConfigRequest


class ModelConfigServiceTests(unittest.TestCase):
    def test_update_provider_config_persists_masked_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = str(Path(temp_dir) / "model-providers.json")
            service = ModelConfigService(config_path)
            snapshot = service.update_provider_config(
                AdminModelConfigUpdateRequest(
                    active_provider="openai",
                    updated_by="tester",
                    provider_config=AdminModelProviderConfigRequest(
                        provider="openai",
                        display_name="OpenAI",
                        api_base_url=" https://api.openai.com/v1 ",
                        model=" gpt-test ",
                        api_key="sk-test-secret",
                        enabled=True,
                    ),
                )
            )

            self.assertEqual(snapshot.active_provider, "openai")
            self.assertEqual(snapshot.updated_by, "tester")
            provider = snapshot.providers[0]
            self.assertTrue(provider.api_key_configured)
            self.assertEqual(provider.api_key_mask, "**********cret")
            self.assertEqual(provider.api_base_url, "https://api.openai.com/v1")
            self.assertEqual(provider.model, "gpt-test")

            reloaded = ModelConfigService(config_path).get_runtime_provider_config("openai")
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.api_key, "sk-test-secret")
            self.assertEqual(reloaded.model, "gpt-test")
            self.assertEqual(reloaded.protocol, "openai_responses")
            self.assertIn("vision", reloaded.capabilities)

    def test_update_provider_config_rejects_invalid_url(self) -> None:
        service = ModelConfigService("")

        with self.assertRaises(ValueError):
            service.update_provider_config(
                AdminModelConfigUpdateRequest(
                    active_provider="openai",
                    provider_config=AdminModelProviderConfigRequest(
                        provider="openai",
                        api_base_url="not-a-url",
                        model="gpt-test",
                        api_key="sk-test",
                    ),
                )
            )

    def test_test_provider_config_reports_missing_config(self) -> None:
        service = ModelConfigService("")

        result = service.test_provider_config("openai")

        self.assertFalse(result.ok)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.checks[0].severity, "error")

    def test_enterprise_private_provider_can_use_trusted_network_without_api_key(self) -> None:
        service = ModelConfigService("")
        snapshot = service.update_provider_config(
            AdminModelConfigUpdateRequest(
                active_provider="enterprise_private",
                provider_config=AdminModelProviderConfigRequest(
                    provider="enterprise_private",
                    api_base_url="http://company-model.internal/v1",
                    model="company-model",
                    api_key="",
                ),
            )
        )
        self.assertEqual(snapshot.providers[0].validation_status, "ok")
        self.assertTrue(service.has_configured_provider("enterprise_private"))

    def test_delete_provider_config_removes_saved_model_and_promotes_remaining_active_provider(self) -> None:
        service = ModelConfigService("")
        service.update_provider_config(
            AdminModelConfigUpdateRequest(
                active_provider="openai",
                provider_config=AdminModelProviderConfigRequest(
                    provider="openai",
                    display_name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    model="gpt-test",
                    api_key="sk-openai",
                ),
            )
        )
        service.update_provider_config(
            AdminModelConfigUpdateRequest(
                active_provider="deepseek",
                provider_config=AdminModelProviderConfigRequest(
                    provider="deepseek",
                    display_name="DeepSeek",
                    api_base_url="https://api.deepseek.com/v1",
                    model="deepseek-chat",
                    api_key="sk-deepseek",
                ),
            )
        )

        snapshot = service.delete_provider_config("deepseek")

        self.assertEqual(snapshot.active_provider, "openai")
        self.assertEqual([provider.provider for provider in snapshot.providers], ["openai"])
        self.assertIsNone(service.get_runtime_provider_config("deepseek"))

    def test_delete_provider_config_rejects_unknown_provider(self) -> None:
        service = ModelConfigService("")

        with self.assertRaises(ValueError):
            service.delete_provider_config("openai")

    def test_schema_one_config_is_migrated_with_explicit_protocol_and_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "model-providers.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_provider": "anthropic",
                        "providers": {
                            "anthropic": {
                                "provider": "anthropic",
                                "api_base_url": "https://api.anthropic.com/v1",
                                "model": "claude-test",
                                "api_key": "secret",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            runtime = ModelConfigService(str(config_path)).get_runtime_provider_config()
            persisted = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(persisted["schema_version"], 2)
            self.assertEqual(runtime.protocol, "anthropic_messages")
            self.assertEqual(runtime.capabilities, ("vision", "streaming", "tool_calling"))

    def test_newer_model_config_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "model-providers.json"
            config_path.write_text(
                json.dumps({"schema_version": 99, "active_provider": "", "providers": {}}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "newer than supported"):
                ModelConfigService(str(config_path))


if __name__ == "__main__":
    unittest.main()
