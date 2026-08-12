"""Provider fallback and retry for the agent loop.

Online providers (OpenAI, DeepSeek, MiniMax...) depend on the public network;
timeouts, rate limits and outages are expected events. ``FallbackAgentProvider``
wraps several providers implementing the ``AgentProvider`` protocol and tries
them in order, with per-provider retries, so a flaky online model can fail over
to a local Ollama model or an enterprise intranet endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from agent.loop import AgentProvider


@dataclass(frozen=True)
class ProviderAttempt:
    provider_label: str
    error: str


class FallbackAgentProvider:
    """Try providers in order; expose which provider served the last call."""

    def __init__(
        self,
        providers: Sequence[AgentProvider],
        *,
        retries: int = 1,
        labels: Optional[Sequence[str]] = None,
    ) -> None:
        if not providers:
            raise ValueError("FallbackAgentProvider requires at least one provider")
        self._providers = list(providers)
        self._retries = max(1, int(retries))
        self._labels = list(labels) if labels else [
            str(getattr(provider, "label", provider.protocol)) for provider in self._providers
        ]
        if len(self._labels) != len(self._providers):
            raise ValueError("labels must match providers")
        self.last_used_provider: Optional[str] = None
        self.attempts: List[ProviderAttempt] = []

    @property
    def protocol(self) -> str:
        return self._providers[0].protocol

    async def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.attempts = []
        self.last_used_provider = None
        last_error: Optional[ProviderAttempt] = None

        for provider, label in zip(self._providers, self._labels):
            for attempt in range(self._retries):
                try:
                    result = await provider.complete(messages, tools)
                    self.last_used_provider = label
                    return result
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    attempt_record = ProviderAttempt(label, error)
                    self.attempts.append(attempt_record)
                    last_error = attempt_record
                    if attempt + 1 < self._retries:
                        continue
                    break

        if last_error is not None:
            raise RuntimeError(
                f"all providers failed (last: {last_error.provider_label}: {last_error.error})"
            ) from None
        raise RuntimeError("no provider attempted")


__all__ = ["FallbackAgentProvider", "ProviderAttempt"]
