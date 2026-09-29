from __future__ import annotations

import pytest

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.search.factory import build_search_provider
from sports_intelligence.providers.search.mock import MockSearchProvider
from sports_intelligence.providers.search.tavily import TavilySearchProvider


def test_build_search_provider_returns_none_when_disabled() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="",
        research_enabled=False,
    )
    provider = build_search_provider(settings)
    assert provider is None


def test_build_search_provider_mock_provider() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
    )
    provider = build_search_provider(settings)
    assert isinstance(provider, MockSearchProvider)
    assert provider.name == "mock"


def test_build_search_provider_tavily_provider() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="tavily",
        search_api_key="tvly-mock-key-12345",
        research_enabled=True,
    )
    provider = build_search_provider(settings)
    assert isinstance(provider, TavilySearchProvider)
    assert provider.name == "tavily"


def test_build_search_provider_tavily_missing_key_raises_config_error() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="tavily",
        search_api_key="",
        research_enabled=True,
    )
    with pytest.raises(ProviderConfigError):
        build_search_provider(settings)


def test_build_search_provider_unsupported_provider_raises_config_error() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="unknown_engine",
        research_enabled=True,
    )
    with pytest.raises(ProviderConfigError):
        build_search_provider(settings)


def test_build_search_provider_mock_override_in_sandbox_env() -> None:
    settings = Settings(
        _env_file=None,
        app_env="sandbox",
        search_provider="mock",
        research_enabled=True,
        research_allow_mock_override=True,
    )
    provider = build_search_provider(settings)
    assert isinstance(provider, MockSearchProvider)
