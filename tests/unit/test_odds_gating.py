"""M4.3 §1/§2 — odds capability gating + outgoing market translation."""

from __future__ import annotations

import httpx
import pytest

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.odds.factory import (
    TheOddsApiProvider,
    build_odds_provider,
)
from sports_intelligence.providers.odds.mock import MockOddsProvider


def _settings(**overrides: object) -> Settings:
    kwargs: dict[str, object] = {"_env_file": None, "app_env": "mock"}
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


def test_mock_env_empty_provider_uses_mock() -> None:
    provider = build_odds_provider(_settings(app_env="mock", odds_provider=""))
    assert isinstance(provider, MockOddsProvider)


def test_live_env_empty_provider_is_disabled_not_mock() -> None:
    """M4.3 §1: sandbox/live_local + empty ODDS_PROVIDER → DISABLED,
    never a silent mock."""
    provider = build_odds_provider(
        _settings(
            app_env="live_local",
            sports_provider="api_football",
            sports_api_key="k",
            odds_provider="",
        )
    )
    assert provider is None


def test_live_env_mock_requires_explicit_override() -> None:
    with pytest.raises(ProviderConfigError):
        build_odds_provider(
            _settings(
                app_env="live_local",
                sports_provider="api_football",
                sports_api_key="k",
                odds_provider="mock",
            )
        )
    provider = build_odds_provider(
        _settings(
            app_env="live_local",
            sports_provider="api_football",
            sports_api_key="k",
            odds_provider="mock",
            odds_allow_mock_override=True,
        )
    )
    assert isinstance(provider, MockOddsProvider)


def test_odds_capability_enabled_property() -> None:
    assert _settings(app_env="mock", odds_provider="").odds_capability_enabled is True
    assert (
        _settings(
            app_env="live_local",
            sports_provider="api_football",
            sports_api_key="k",
            odds_provider="",
        ).odds_capability_enabled
        is False
    )
    assert (
        _settings(
            app_env="live_local",
            sports_provider="api_football",
            sports_api_key="k",
            odds_provider="the_odds_api",
            odds_api_key="ok",
        ).odds_capability_enabled
        is True
    )


def test_request_markets_adds_alternate_totals() -> None:
    """M4.3 §2: internal requirements (1X2 / DC / O-U 1.5 / O-U 2.5 /
    BTTS) translate to provider keys sufficient to retrieve exact O/U
    lines: totals + alternate_totals."""
    provider = TheOddsApiProvider(api_key="k", base_url="https://x.test")
    markets = provider.request_markets(["h2h", "double_chance", "totals", "btts"])
    assert "totals" in markets
    assert "alternate_totals" in markets
    assert len(markets) == 5


def test_outgoing_query_contains_alternate_totals() -> None:
    """Contract test: the actual HTTP query for event odds must request
    alternate_totals (exact O/U 1.5/2.5 lines)."""
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "id": "evt-1",
                "home_team": "A",
                "away_team": "B",
                "last_update": "2026-08-21T10:00:00Z",
                "bookmakers": [
                    {
                        "key": "sb",
                        "title": "SB",
                        "markets": [
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over 2.5", "price": 1.85, "point": 2.5},
                                    {"name": "Under 2.5", "price": 1.95, "point": 2.5},
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    provider = TheOddsApiProvider(
        api_key="k",
        base_url="https://x.test/v4",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        backoff_seconds=0.001,
    )

    import asyncio

    async def _run() -> None:
        markets = provider.request_markets(["h2h", "double_chance", "totals", "btts"])
        await provider.fetch_event_odds(
            sport_key="soccer_epl", event_id="evt-1", markets=markets, regions=["eu"]
        )

    asyncio.run(_run())
    assert "markets" in captured_params
    sent = captured_params["markets"].split(",")
    assert "alternate_totals" in sent
    assert "totals" in sent
    assert "h2h" in sent
    assert "double_chance" in sent
    assert "btts" in sent


def test_cost_uses_actual_provider_market_set() -> None:
    """5 provider markets × 1 region → estimated cost 5."""
    provider = TheOddsApiProvider(api_key="k", base_url="https://x.test")
    actual = provider.request_markets(["h2h", "double_chance", "totals", "btts"])
    assert provider.estimate_cost(markets=actual, regions=["eu"]) == 5
