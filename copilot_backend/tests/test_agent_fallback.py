import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.fallback import FallbackAgentProvider


class FakeProvider:
    protocol = "openai_chat"

    def __init__(self, label: str, failures: int = 0, result: dict | None = None) -> None:
        self.label = label
        self.failures = failures
        self.calls = 0
        self._result = result or {"role": "assistant", "content": f"from {label}", "tool_calls": []}

    async def complete(self, messages, tools):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"{self.label} network down")
        return self._result


@pytest.mark.asyncio
async def test_falls_back_to_next_provider():
    primary = FakeProvider("deepseek-v4-flash", failures=1)
    local = FakeProvider("ollama-qwen3")
    fallback = FallbackAgentProvider([primary, local])

    result = await fallback.complete([], [])

    assert result["content"] == "from ollama-qwen3"
    assert fallback.last_used_provider == "ollama-qwen3"
    assert primary.calls == 1
    assert local.calls == 1
    assert len(fallback.attempts) == 1
    assert fallback.attempts[0].provider_label == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_retries_within_provider_before_failover():
    primary = FakeProvider("deepseek", failures=2)
    local = FakeProvider("ollama")
    fallback = FallbackAgentProvider([primary, local], retries=2)

    result = await fallback.complete([], [])

    assert result["content"] == "from ollama"
    assert primary.calls == 2
    assert fallback.last_used_provider == "ollama"


@pytest.mark.asyncio
async def test_first_provider_success_skips_others():
    primary = FakeProvider("deepseek")
    local = FakeProvider("ollama")
    fallback = FallbackAgentProvider([primary, local])

    result = await fallback.complete([], [])

    assert result["content"] == "from deepseek"
    assert fallback.last_used_provider == "deepseek"
    assert local.calls == 0
    assert fallback.attempts == []


@pytest.mark.asyncio
async def test_all_providers_failed_raises():
    primary = FakeProvider("deepseek", failures=5)
    local = FakeProvider("ollama", failures=5)
    fallback = FallbackAgentProvider([primary, local], retries=1)

    with pytest.raises(RuntimeError) as exc:
        await fallback.complete([], [])

    assert "all providers failed" in str(exc.value)
    assert len(fallback.attempts) == 2
