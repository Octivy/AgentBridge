from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from gateway.provider_client import call_provider, resolve_provider_settings, sanitize_response_text
from shared.schemas import ChatMessageRequest


ProviderCaller = Callable[[ChatMessageRequest, Optional[str], Optional[str]], Awaitable[str]]


@dataclass(frozen=True)
class ModelGatewayResult:
    text: str
    provider: str
    provider_display_name: str
    model: str
    trace_id: str = ""
    estimated_tokens: int = 0


class GatewayModelService:
    def __init__(self, provider_caller: ProviderCaller = call_provider) -> None:
        self._provider_caller = provider_caller

    async def request_text_result(
        self,
        request: ChatMessageRequest,
        system_prompt_override: Optional[str] = None,
        user_message_override: Optional[str] = None,
    ) -> ModelGatewayResult:
        settings = resolve_provider_settings(request)
        prompt_tokens = estimate_text_tokens((system_prompt_override or "") + "\n" + (user_message_override or request.message or ""))
        raw_text = await self._provider_caller(request, system_prompt_override, user_message_override)
        sanitized = sanitize_response_text(raw_text)
        estimated_tokens = prompt_tokens + estimate_text_tokens(sanitized)
        return ModelGatewayResult(
            text=sanitized,
            provider=settings.provider,
            provider_display_name=settings.display_name,
            model=settings.model,
            trace_id=(request.trace_id or ""),
            estimated_tokens=estimated_tokens,
        )

    async def request_text(
        self,
        request: ChatMessageRequest,
        system_prompt_override: Optional[str] = None,
        user_message_override: Optional[str] = None,
    ) -> str:
        result = await self.request_text_result(request, system_prompt_override, user_message_override)
        return result.text


gateway_model_service = GatewayModelService()


def estimate_text_tokens(value: str) -> int:
    text = value or ""
    if not text.strip():
        return 1
    return max((len(text) + 3) // 4, 1)
