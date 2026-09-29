from __future__ import annotations

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.search.base import SearchProvider
from sports_intelligence.providers.search.mock import MockSearchProvider
from sports_intelligence.providers.search.tavily import TavilySearchProvider


def build_search_provider(settings: Settings) -> SearchProvider | None:
    """Build the configured search provider according to environment gating.

    Rules:
    - empty SEARCH_PROVIDER → returns None (research capability DISABLED);
    - APP_ENV=mock + search_provider="mock" (or empty) → MockSearchProvider;
    - APP_ENV=sandbox/live_local + search_provider="mock" → only allowed if
      research_allow_mock_override=True, otherwise ProviderConfigError;
    - search_provider="tavily" → requires SEARCH_API_KEY;
    - unsupported search_provider → ProviderConfigError.
    """
    if not settings.research_enabled:
        return None

    raw_name = (settings.search_provider or "").strip().lower()

    if not raw_name:
        if settings.app_env == "mock":
            return MockSearchProvider()
        return None

    if raw_name == "mock":
        if settings.app_env == "mock" or settings.research_allow_mock_override:
            return MockSearchProvider()
        raise ProviderConfigError(
            "Mock search provider refused in non-mock environment "
            "without research_allow_mock_override=True"
        )

    if raw_name == "tavily":
        if not settings.search_api_key:
            raise ProviderConfigError("SEARCH_API_KEY is required for tavily search provider")
        return TavilySearchProvider(
            api_key=settings.search_api_key,
            base_url=settings.tavily_base_url,
        )

    raise ProviderConfigError(f"Unsupported search provider: {settings.search_provider!r}")
