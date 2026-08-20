from __future__ import annotations

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.sports.api_football import ApiFootballProvider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider


def build_sports_provider(settings: Settings) -> SportsDataProvider:
    if settings.sports_provider == "api_football":
        return ApiFootballProvider(
            api_key=settings.sports_api_key,
            base_url=settings.api_football_base_url,
        )
    return MockSportsDataProvider()
