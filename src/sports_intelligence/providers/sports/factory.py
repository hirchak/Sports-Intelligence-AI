from __future__ import annotations

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.sports.api_football import ApiFootballProvider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider

SUPPORTED_PROVIDERS = ("mock", "api_football")


def build_sports_provider(settings: Settings) -> SportsDataProvider:
    provider_name = settings.sports_provider
    if provider_name == "mock":
        return MockSportsDataProvider()
    if provider_name == "api_football":
        return ApiFootballProvider(
            api_key=settings.sports_api_key,
            base_url=settings.api_football_base_url,
        )
    raise ProviderConfigError(
        f"unknown SPORTS_PROVIDER {provider_name!r}; "
        f"supported providers: {', '.join(SUPPORTED_PROVIDERS)}"
    )
