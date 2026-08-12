from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from shared import settings
from shared.schemas import (
    AdminModelConfigResponse,
    AdminModelConfigTestResponse,
    AdminModelConfigUpdateRequest,
    AdminModelProviderConfigRequest,
    AdminModelProviderConfigResponse,
    AdminModelProviderPresetResponse,
    AdminValidationCheckResponse,
)


@dataclass(frozen=True)
class RuntimeModelProviderConfig:
    provider: str
    display_name: str
    api_key: str
    api_base_url: str
    model: str
    enabled: bool = True
    protocol: str = "openai_chat"
    capabilities: tuple[str, ...] = ()


MODEL_CONFIG_SCHEMA_VERSION = 2
SUPPORTED_PROTOCOLS = {"openai_chat", "openai_responses", "anthropic_messages"}


MODEL_PROVIDER_PRESETS = [
    AdminModelProviderPresetResponse(
        provider="cadcopilot",
        display_name="AgentBridge Official",
        description="中心端统一模型代理。适合正式发布或企业内网统一转接。",
        default_base_url=settings.CADCOPILOT_OFFICIAL_BASE_URL,
        default_model=settings.CADCOPILOT_OFFICIAL_MODEL,
        api_key_hint="填写中心模型代理或企业模型服务的 API Key。",
    ),
    AdminModelProviderPresetResponse(
        provider="minimax",
        display_name="MiniMax",
        description="MiniMax 官方 OpenAI-compatible 接口。",
        default_base_url=settings.MINIMAX_BASE_URL,
        default_model=settings.MINIMAX_MODEL,
        api_key_hint="填写 MiniMax API Key。",
    ),
    AdminModelProviderPresetResponse(
        provider="openai",
        display_name="OpenAI",
        description="OpenAI 官方接口或兼容网关。",
        default_base_url=settings.OPENAI_BASE_URL,
        default_model=settings.OPENAI_MODEL,
        api_key_hint="填写 OpenAI API Key。",
    ),
    AdminModelProviderPresetResponse(
        provider="anthropic",
        display_name="Anthropic",
        description="Anthropic 原生 Messages API。",
        default_base_url=settings.ANTHROPIC_BASE_URL,
        default_model=settings.ANTHROPIC_MODEL,
        api_key_hint="填写 Anthropic API Key。",
    ),
    AdminModelProviderPresetResponse(
        provider="deepseek",
        display_name="DeepSeek",
        description="DeepSeek 官方 OpenAI-compatible 接口。",
        default_base_url=settings.DEEPSEEK_BASE_URL,
        default_model=settings.DEEPSEEK_MODEL,
        api_key_hint="填写 DeepSeek API Key。",
    ),
    AdminModelProviderPresetResponse(
        provider="openai_compatible",
        display_name="OpenAI Compatible",
        description="任意兼容 /chat/completions 的模型服务。",
        default_base_url="https://model-provider.example.com/v1",
        default_model="model-name",
        api_key_hint="填写兼容服务的 Bearer Token。",
    ),
    AdminModelProviderPresetResponse(
        provider="ollama",
        display_name="Ollama",
        description="本机 Ollama OpenAI-compatible 接口；默认无需 API Key。",
        default_base_url=settings.OLLAMA_BASE_URL,
        default_model=settings.OLLAMA_MODEL,
        api_key_hint="本机默认留空；仅在代理要求鉴权时填写。",
    ),
    AdminModelProviderPresetResponse(
        provider="enterprise_private",
        display_name="Enterprise Private Model",
        description="企业自建模型服务或内网推理网关。",
        default_base_url="https://model-gateway.internal.example.com/v1",
        default_model="enterprise-default",
        api_key_hint="填写企业网关分配的服务密钥。",
    ),
]


class ModelConfigService:
    def __init__(self, config_path: str = settings.CADCOPILOT_MODEL_CONFIG_PATH) -> None:
        self._config_path = Path(config_path) if config_path else None
        self._state: dict[str, Any] = self._load_state()
        if self._migrate_state(self._state):
            self._persist_state()

    def list_presets(self) -> list[AdminModelProviderPresetResponse]:
        return list(MODEL_PROVIDER_PRESETS)

    def get_config_snapshot(self) -> AdminModelConfigResponse:
        state = self._load_state()
        providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
        return AdminModelConfigResponse(
            active_provider=str(state.get("active_provider") or ""),
            providers=[
                self._build_provider_response(provider_id, provider_data)
                for provider_id, provider_data in sorted(providers.items())
                if isinstance(provider_data, dict)
            ],
            updated_at=_parse_datetime(state.get("updated_at")),
            updated_by=str(state.get("updated_by") or ""),
            persistence_enabled=self._config_path is not None,
            persistence_path=str(self._config_path or ""),
        )

    def update_provider_config(self, request: AdminModelConfigUpdateRequest) -> AdminModelConfigResponse:
        provider = _normalize_runtime_provider(request.active_provider)
        provider_config = request.provider_config
        config_provider = _normalize_runtime_provider(provider_config.provider)
        if config_provider != provider:
            raise ValueError("active_provider must match provider_config.provider")

        messages = _validate_provider_config(provider_config)
        errors = [message for severity, message in messages if severity == "error"]
        if errors:
            raise ValueError("; ".join(errors))

        state = self._load_state()
        providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
        previous = providers.get(provider) if isinstance(providers.get(provider), dict) else {}
        api_key = provider_config.api_key if provider_config.api_key is not None else str(previous.get("api_key") or "")
        updated_at = _utc_now()
        providers[provider] = {
            "provider": provider,
            "display_name": (provider_config.display_name or _display_name_for_provider(provider)).strip(),
            "api_base_url": provider_config.api_base_url.strip().rstrip("/"),
            "model": provider_config.model.strip(),
            "api_key": api_key.strip(),
            "enabled": bool(provider_config.enabled),
            "protocol": (provider_config.protocol or _default_protocol(provider)).strip(),
            "capabilities": list(provider_config.capabilities or _default_capabilities(provider)),
            "updated_at": updated_at.isoformat(),
        }

        state = {
            "schema_version": MODEL_CONFIG_SCHEMA_VERSION,
            "active_provider": provider,
            "providers": providers,
            "updated_at": updated_at.isoformat(),
            "updated_by": (request.updated_by or "admin").strip() or "admin",
        }
        self._state = state
        self._persist_state()
        return self.get_config_snapshot()

    def delete_provider_config(self, provider: str) -> AdminModelConfigResponse:
        provider_id = _normalize_runtime_provider(provider)
        if not provider_id:
            raise ValueError("provider is required")

        state = self._load_state()
        providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
        if provider_id not in providers:
            raise ValueError("provider is not configured")

        providers.pop(provider_id, None)
        active_provider = str(state.get("active_provider") or "")
        if _normalize_runtime_provider(active_provider) == provider_id:
            active_provider = sorted(providers.keys())[0] if providers else ""

        updated_at = _utc_now()
        state = {
            "schema_version": MODEL_CONFIG_SCHEMA_VERSION,
            "active_provider": active_provider,
            "providers": providers,
            "updated_at": updated_at.isoformat(),
            "updated_by": "web-admin",
        }
        self._state = state
        self._persist_state()
        return self.get_config_snapshot()

    def test_provider_config(self, provider: Optional[str] = None) -> AdminModelConfigTestResponse:
        runtime = self.get_runtime_provider_config(provider)
        provider_id = _normalize_runtime_provider(provider) if provider else self.get_config_snapshot().active_provider
        if runtime is None:
            return AdminModelConfigTestResponse(
                ok=False,
                provider=provider_id or "",
                checks=[
                    AdminValidationCheckResponse(
                        severity="error",
                        message="模型 provider 尚未配置，请先保存 provider、base_url、model 和 API Key。",
                    )
                ],
            )

        checks = _runtime_config_checks(runtime)
        ok = not any(check.severity == "error" for check in checks)
        return AdminModelConfigTestResponse(
            ok=ok,
            provider=runtime.provider,
            display_name=runtime.display_name,
            checks=checks,
        )

    def get_runtime_provider_config(self, provider: Optional[str] = None) -> Optional[RuntimeModelProviderConfig]:
        state = self._load_state()
        provider_id = _normalize_runtime_provider(provider or str(state.get("active_provider") or ""))
        providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
        provider_data = providers.get(provider_id)
        if not isinstance(provider_data, dict):
            return None

        runtime = RuntimeModelProviderConfig(
            provider=provider_id,
            display_name=str(provider_data.get("display_name") or _display_name_for_provider(provider_id)),
            api_key=str(provider_data.get("api_key") or "").strip(),
            api_base_url=str(provider_data.get("api_base_url") or "").strip().rstrip("/"),
            model=str(provider_data.get("model") or "").strip(),
            enabled=bool(provider_data.get("enabled", True)),
            protocol=str(provider_data.get("protocol") or _default_protocol(provider_id)),
            capabilities=tuple(provider_data.get("capabilities") or _default_capabilities(provider_id)),
        )
        if not runtime.enabled:
            return None
        return runtime

    def has_configured_provider(self, provider: Optional[str] = None) -> bool:
        runtime = self.get_runtime_provider_config(provider)
        return bool(
            runtime
            and runtime.api_base_url
            and runtime.model
            and (
                runtime.api_key
                or _normalize_runtime_provider(runtime.provider)
                in {"ollama", "openai_compatible", "enterprise_private"}
            )
        )

    def _build_provider_response(self, provider_id: str, provider_data: dict[str, Any]) -> AdminModelProviderConfigResponse:
        provider = _normalize_runtime_provider(provider_id)
        api_key = str(provider_data.get("api_key") or "").strip()
        request = AdminModelProviderConfigRequest(
            provider=provider,
            display_name=str(provider_data.get("display_name") or _display_name_for_provider(provider)),
            api_base_url=str(provider_data.get("api_base_url") or ""),
            model=str(provider_data.get("model") or ""),
            api_key=api_key,
            enabled=bool(provider_data.get("enabled", True)),
            protocol=str(provider_data.get("protocol") or _default_protocol(provider)),
            capabilities=list(provider_data.get("capabilities") or _default_capabilities(provider)),
        )
        messages = _validate_provider_config(request)
        return AdminModelProviderConfigResponse(
            provider=provider,
            display_name=request.display_name or _display_name_for_provider(provider),
            api_base_url=request.api_base_url,
            model=request.model,
            enabled=request.enabled,
            api_key_configured=bool(api_key),
            api_key_mask=_mask_secret(api_key),
            updated_at=_parse_datetime(provider_data.get("updated_at")),
            validation_status="ok" if not any(severity == "error" for severity, _ in messages) else "invalid",
            validation_messages=[message for _, message in messages],
            protocol=request.protocol or _default_protocol(provider),
            capabilities=list(request.capabilities),
        )

    def _load_state(self) -> dict[str, Any]:
        if self._config_path is None or not self._config_path.exists():
            return dict(self._state) if hasattr(self, "_state") else {"active_provider": "", "providers": {}}

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active_provider": "", "providers": {}}

        if not isinstance(raw, dict):
            return {"active_provider": "", "providers": {}}
        providers = raw.get("providers")
        if not isinstance(providers, dict):
            raw["providers"] = {}
        return raw

    @staticmethod
    def _migrate_state(state: dict[str, Any]) -> bool:
        changed = False
        version = int(state.get("schema_version") or 1)
        if version > MODEL_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"Model config schema {version} is newer than supported schema {MODEL_CONFIG_SCHEMA_VERSION}."
            )
        providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
        state["providers"] = providers
        for provider_id, provider_data in providers.items():
            if not isinstance(provider_data, dict):
                continue
            if not provider_data.get("protocol"):
                provider_data["protocol"] = _default_protocol(provider_id)
                changed = True
            if not isinstance(provider_data.get("capabilities"), list):
                provider_data["capabilities"] = list(_default_capabilities(provider_id))
                changed = True
        if version < MODEL_CONFIG_SCHEMA_VERSION:
            state["schema_version"] = MODEL_CONFIG_SCHEMA_VERSION
            changed = True
        return changed

    def _persist_state(self) -> None:
        if self._config_path is None:
            return

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self._config_path)


def list_model_provider_presets() -> list[AdminModelProviderPresetResponse]:
    return model_config_service.list_presets()


def get_model_config_snapshot() -> AdminModelConfigResponse:
    return model_config_service.get_config_snapshot()


def get_runtime_model_provider_config(provider: Optional[str] = None) -> Optional[RuntimeModelProviderConfig]:
    return model_config_service.get_runtime_provider_config(provider)


def has_configured_center_model_provider(provider: Optional[str] = None) -> bool:
    return model_config_service.has_configured_provider(provider)


def _validate_provider_config(request: AdminModelProviderConfigRequest) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    provider = _normalize_runtime_provider(request.provider)
    if not provider:
        messages.append(("error", "provider 不能为空。"))
    if not (request.api_base_url or "").strip():
        messages.append(("error", "api_base_url 不能为空。"))
    elif not _is_http_url(request.api_base_url):
        messages.append(("error", "api_base_url 必须是 http 或 https URL。"))
    if not (request.model or "").strip():
        messages.append(("error", "model 不能为空。"))
    if not (request.api_key or "").strip() and provider not in {"ollama", "openai_compatible", "enterprise_private"}:
        messages.append(("warning", "API Key 未配置，保存后仍无法调用真实模型。"))
    protocol = (request.protocol or _default_protocol(provider)).strip()
    if protocol not in SUPPORTED_PROTOCOLS:
        messages.append(("error", f"不支持的 protocol: {protocol}"))
    supported_capabilities = {"vision", "structured_output", "streaming", "tool_calling"}
    unknown_capabilities = sorted(set(request.capabilities) - supported_capabilities)
    if unknown_capabilities:
        messages.append(("error", "不支持的 capability: " + ", ".join(unknown_capabilities)))
    return messages


def _runtime_config_checks(runtime: RuntimeModelProviderConfig) -> list[AdminValidationCheckResponse]:
    request = AdminModelProviderConfigRequest(
        provider=runtime.provider,
        display_name=runtime.display_name,
        api_base_url=runtime.api_base_url,
        model=runtime.model,
        api_key=runtime.api_key,
        enabled=runtime.enabled,
        protocol=runtime.protocol,
        capabilities=list(runtime.capabilities),
    )
    checks = [
        AdminValidationCheckResponse(severity=severity, message=message)
        for severity, message in _validate_provider_config(request)
    ]
    if runtime.enabled:
        checks.append(AdminValidationCheckResponse(severity="info", message="配置已启用。"))
    else:
        checks.append(AdminValidationCheckResponse(severity="error", message="配置已停用。"))
    if (
        runtime.api_key
        or _normalize_runtime_provider(runtime.provider) in {"ollama", "openai_compatible", "enterprise_private"}
    ) and runtime.api_base_url and runtime.model:
        checks.append(AdminValidationCheckResponse(severity="info", message="静态校验通过；真实连通性将在模型调用或后续在线测试中确认。"))
    return checks


def _normalize_runtime_provider(provider: Optional[str]) -> str:
    normalized = (provider or "").strip().lower().replace("-", "_")
    if normalized in {"official", "cad_copilot"}:
        return "cadcopilot"
    return normalized


def _display_name_for_provider(provider: str) -> str:
    normalized = _normalize_runtime_provider(provider)
    for preset in MODEL_PROVIDER_PRESETS:
        if preset.provider == normalized:
            return preset.display_name
    return normalized or "Model Provider"


def _default_protocol(provider: str) -> str:
    normalized = _normalize_runtime_provider(provider)
    if normalized == "openai":
        return "openai_responses"
    if normalized == "anthropic":
        return "anthropic_messages"
    return "openai_chat"


def _default_capabilities(provider: str) -> tuple[str, ...]:
    normalized = _normalize_runtime_provider(provider)
    if normalized == "openai":
        return ("vision", "structured_output", "streaming", "tool_calling")
    if normalized == "anthropic":
        return ("vision", "streaming", "tool_calling")
    if normalized == "ollama":
        return ("vision", "structured_output", "streaming", "tool_calling")
    return ("structured_output", "streaming", "tool_calling")


def _is_http_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _mask_secret(value: str) -> str:
    secret = (value or "").strip()
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{'*' * max(len(secret) - 4, 4)}{secret[-4:]}"


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


model_config_service = ModelConfigService()
