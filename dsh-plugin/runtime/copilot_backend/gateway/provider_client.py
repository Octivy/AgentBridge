import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from gateway.provider_adapters import (
    ProviderInvocation,
    ProviderResponseError,
    get_provider_adapter,
    negotiate_capabilities,
)
from product.model_config_service import get_runtime_model_provider_config
from shared.schemas import ChatMessageRequest
from shared.settings import (
    AGENT_SYSTEM_PROMPT,
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MODEL,
    CADCOPILOT_OFFICIAL_API_KEY,
    CADCOPILOT_OFFICIAL_BASE_URL,
    CADCOPILOT_OFFICIAL_MODEL,
    CHAT_SYSTEM_PROMPT,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    MINIMAX_API_KEY,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SERVICE_TIMEOUT_SECONDS,
)


@dataclass(frozen=True)
class ModelProviderSettings:
    provider: str
    display_name: str
    api_key: str
    api_base_url: str
    model: str
    protocol: str = "openai_chat"
    requires_api_key: bool = True
    capabilities: tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_provider(provider: Optional[str]) -> str:
    normalized = (provider or "").strip().lower()
    if not normalized:
        return "cadcopilot"
    if normalized in {"cadcopilot", "official", "cad_copilot", "cad-copilot"}:
        return "cadcopilot"
    if normalized in {"gpt", "gpt-5", "gpt-5.5", "openai"}:
        return "openai"
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    if normalized == "deepseek":
        return "deepseek"
    if normalized in {"openai_compatible", "openai-compatible", "compatible"}:
        return "openai_compatible"
    if normalized in {"ollama", "local"}:
        return "ollama"
    if normalized in {"enterprise_private", "enterprise-private"}:
        return "enterprise_private"
    if normalized == "minimax":
        return "minimax"
    return normalized


def resolve_provider_settings(request: ChatMessageRequest) -> ModelProviderSettings:
    provider = normalize_provider(request.provider)
    runtime_provider = _resolve_runtime_provider_settings(request, provider)
    if runtime_provider is not None:
        return runtime_provider

    if provider == "cadcopilot":
        return ModelProviderSettings(
            provider=provider,
            display_name="AgentBridge Official",
            api_key=(CADCOPILOT_OFFICIAL_API_KEY or "").strip(),
            api_base_url=(CADCOPILOT_OFFICIAL_BASE_URL or MINIMAX_BASE_URL).strip(),
            model=(request.model or CADCOPILOT_OFFICIAL_MODEL or MINIMAX_MODEL).strip() or MINIMAX_MODEL,
            protocol=(request.protocol or "openai_chat").strip(),
            capabilities=tuple(request.capabilities or ("structured_output", "streaming", "tool_calling")),
        )

    if provider == "openai":
        return ModelProviderSettings(
            provider=provider,
            display_name="OpenAI",
            api_key=(request.api_key or OPENAI_API_KEY or "").strip(),
            api_base_url=(request.api_base_url or OPENAI_BASE_URL).strip(),
            model=(request.model or OPENAI_MODEL).strip() or OPENAI_MODEL,
            protocol=(request.protocol or "openai_responses").strip(),
            capabilities=tuple(request.capabilities or ("vision", "structured_output", "streaming", "tool_calling")),
        )

    if provider == "anthropic":
        return ModelProviderSettings(
            provider=provider,
            display_name="Anthropic",
            api_key=(request.api_key or ANTHROPIC_API_KEY or "").strip(),
            api_base_url=(request.api_base_url or ANTHROPIC_BASE_URL).strip(),
            model=(request.model or ANTHROPIC_MODEL).strip() or ANTHROPIC_MODEL,
            protocol=(request.protocol or "anthropic_messages").strip(),
            capabilities=tuple(request.capabilities or ("vision", "streaming", "tool_calling")),
        )

    if provider == "deepseek":
        return ModelProviderSettings(
            provider=provider,
            display_name="DeepSeek",
            api_key=(request.api_key or DEEPSEEK_API_KEY or "").strip(),
            api_base_url=(request.api_base_url or DEEPSEEK_BASE_URL).strip(),
            model=(request.model or DEEPSEEK_MODEL).strip() or DEEPSEEK_MODEL,
            protocol=(request.protocol or "openai_chat").strip(),
            capabilities=tuple(request.capabilities or ("structured_output", "streaming", "tool_calling")),
        )

    if provider == "openai_compatible":
        return ModelProviderSettings(
            provider=provider,
            display_name="OpenAI Compatible",
            api_key=(request.api_key or "").strip(),
            api_base_url=(request.api_base_url or "").strip(),
            model=(request.model or "").strip(),
            protocol=(request.protocol or "openai_chat").strip(),
            requires_api_key=False,
            capabilities=tuple(request.capabilities),
        )

    if provider == "ollama":
        return ModelProviderSettings(
            provider=provider,
            display_name="Ollama",
            api_key=(request.api_key or "").strip(),
            api_base_url=(request.api_base_url or OLLAMA_BASE_URL).strip(),
            model=(request.model or OLLAMA_MODEL).strip() or OLLAMA_MODEL,
            protocol=(request.protocol or "openai_chat").strip(),
            requires_api_key=False,
            capabilities=tuple(request.capabilities or ("vision", "structured_output", "streaming", "tool_calling")),
        )

    if provider == "enterprise_private":
        return ModelProviderSettings(
            provider=provider,
            display_name="Enterprise Private Model",
            api_key=(request.api_key or "").strip(),
            api_base_url=(request.api_base_url or "").strip(),
            model=(request.model or "").strip(),
            protocol=(request.protocol or "openai_chat").strip(),
            requires_api_key=False,
            capabilities=tuple(request.capabilities),
        )

    if provider != "minimax":
        raise HTTPException(status_code=400, detail=f"不支持的模型 provider: {provider}")

    return ModelProviderSettings(
        provider="minimax",
        display_name="MiniMax",
        api_key=(request.api_key or MINIMAX_API_KEY or "").strip(),
        api_base_url=(request.api_base_url or MINIMAX_BASE_URL).strip(),
        model=(request.model or MINIMAX_MODEL).strip() or MINIMAX_MODEL,
        protocol=(request.protocol or "openai_chat").strip(),
        capabilities=tuple(request.capabilities or ("structured_output", "streaming", "tool_calling")),
    )


def _resolve_runtime_provider_settings(request: ChatMessageRequest, provider: str) -> Optional[ModelProviderSettings]:
    if request.api_key:
        return None

    runtime = get_runtime_model_provider_config()
    if runtime is not None and (provider == "cadcopilot" or _runtime_matches_provider(runtime.provider, provider)):
        return _runtime_settings(runtime, request, provider)

    runtime = get_runtime_model_provider_config(provider)
    if runtime is not None and _runtime_matches_provider(runtime.provider, provider):
        return _runtime_settings(runtime, request, provider)

    return None


def _runtime_settings(runtime, request: ChatMessageRequest, provider: str) -> ModelProviderSettings:
    runtime_provider = normalize_provider(runtime.provider)
    return ModelProviderSettings(
        provider="cadcopilot" if provider == "cadcopilot" else runtime.provider,
        display_name=runtime.display_name,
        api_key=runtime.api_key,
        api_base_url=runtime.api_base_url,
        model=(request.model or runtime.model).strip() or runtime.model,
        protocol=runtime.protocol,
        requires_api_key=runtime_provider not in {"ollama", "openai_compatible", "enterprise_private"},
        capabilities=tuple(runtime.capabilities),
    )


def _runtime_matches_provider(runtime_provider: str, requested_provider: str) -> bool:
    return normalize_provider(runtime_provider) == requested_provider


def get_provider_settings(request: ChatMessageRequest) -> Dict[str, Any]:
    return resolve_provider_settings(request).as_dict()


def build_provider_error(display_name: str, status_code: int, response_text: str) -> str:
    body = (response_text or "").lower()
    if status_code in {401, 403} or "invalid api key" in body or "incorrect api key" in body or "unauthorized" in body:
        return f"{display_name} API Key 不正确，或当前 Key 没有访问权限。"

    if status_code == 429 or "quota" in body or "balance" in body or "credit" in body or "billing" in body or "insufficient" in body:
        return f"{display_name} 账户额度不足、额度已用尽，或请求频率受限。"

    if status_code == 404 or "model_not_found" in body or "not found" in body or "does not exist" in body:
        return f"{display_name} 模型不可用，或模型名称不正确。"

    return f"{display_name} 连接失败: HTTP {status_code} {response_text}".strip()


async def call_provider(
    request: ChatMessageRequest,
    system_prompt_override: Optional[str] = None,
    user_message_override: Optional[str] = None,
) -> str:
    settings = resolve_provider_settings(request)
    if settings.requires_api_key and not settings.api_key:
        raise HTTPException(status_code=400, detail=f"{settings.display_name} API Key 未配置。")
    if not settings.api_base_url:
        raise HTTPException(status_code=400, detail=f"{settings.display_name} API 地址未配置。")
    if not settings.model:
        raise HTTPException(status_code=400, detail=f"{settings.display_name} 模型名称未配置。")

    user_message = (user_message_override or request.message).strip() or "请分析上传内容并给出 CAD 建议。"
    system_prompt = system_prompt_override or (
        AGENT_SYSTEM_PROMPT if (request.mode or "").strip().lower() == "draw" else CHAT_SYSTEM_PROMPT
    )

    try:
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT_SECONDS) as client:
            adapter = get_provider_adapter(settings.protocol)
            negotiated = adapter.capabilities
            configured = set(settings.capabilities)
            if configured:
                negotiated = type(negotiated)(
                    vision=negotiated.vision and "vision" in configured,
                    structured_output=negotiated.structured_output and "structured_output" in configured,
                    streaming=negotiated.streaming and "streaming" in configured,
                    tool_calling=negotiated.tool_calling and "tool_calling" in configured,
                )
                adapter = _CapabilityBoundAdapter(adapter, negotiated)
            negotiate_capabilities(
                adapter,
                image_requested=bool(request.image_base64),
                structured_output_requested=bool(request.response_schema),
                streaming_requested=bool(request.stream),
                tool_calling_requested=bool(request.tools),
            )
            return await adapter.generate(
                client,
                ProviderInvocation(
                    display_name=settings.display_name,
                    api_key=settings.api_key,
                    api_base_url=settings.api_base_url,
                    model=settings.model,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    image_base64=request.image_base64 or "",
                    response_schema=request.response_schema,
                    tools=tuple(request.tools),
                    stream=request.stream,
                ),
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="连接超时，请检查网络、接口地址或模型服务状态。")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"连接失败，请检查网络连接或接口地址。详情: {exc}")
    except ProviderResponseError as exc:
        raise HTTPException(
            status_code=502,
            detail=build_provider_error(settings.display_name, exc.status_code, exc.response_text),
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"{settings.display_name} 返回了无法识别的响应: {exc}")


def sanitize_response_text(raw_text: str) -> str:
    if not raw_text:
        return ""

    return re.sub(r"<think>.*?</think>\s*", "", raw_text, flags=re.DOTALL).strip()


class _CapabilityBoundAdapter:
    def __init__(self, adapter, capabilities) -> None:
        self._adapter = adapter
        self.capabilities = capabilities

    async def generate(self, client, invocation):
        return await self._adapter.generate(client, invocation)
