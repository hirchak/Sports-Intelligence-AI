from __future__ import annotations

import httpx

from sports_intelligence.core.config import Settings
from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.providers.llm.base import LLMError, LLMProvider
from sports_intelligence.providers.llm.http import (
    MiniMaxProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    OpenCodeGoProvider,
)
from sports_intelligence.providers.llm.mock import MockLLMProvider


def build_llm_provider(
    settings: Settings,
    config: ModelSpec,
    *,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMProvider:
    if config.provider == "mock":
        if not settings.is_mock_mode:
            raise LLMError("mock_forbidden_in_non_mock")
        return MockLLMProvider()
    classes = {
        "openai": OpenAIProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "minimax": MiniMaxProvider,
        "opencode_go": OpenCodeGoProvider,
    }
    if config.provider not in classes:
        raise LLMError("unknown_provider")
    if config.provider == "opencode_go" and not settings.llm_opencode_go_runtime_allowed:
        raise LLMError("opencode_go_runtime_not_authorized")
    keys = {
        "openai": settings.llm_openai_api_key,
        "openai_compatible": settings.llm_openai_api_key,
        "minimax": settings.llm_minimax_api_key,
        "opencode_go": settings.llm_opencode_go_api_key,
    }
    key = keys[config.provider]
    if not key and settings.llm_provider == config.provider:
        key = settings.llm_api_key
    defaults = {
        "openai": "https://api.openai.com/v1",
        "minimax": "https://api.minimax.io/v1",
        "opencode_go": "https://opencode.ai/zen/go/v1",
    }
    url = config.base_url or defaults.get(config.provider)
    if not url:
        raise LLMError("missing_base_url")
    return classes[config.provider](
        provider=config.provider,
        api_key=key,
        base_url=url,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
