"""M4.2 §4/§5/§7 — The Odds API event/sport-key mapping + markets.

- GET /v4/sports/{sport}/events returns a TOP-LEVEL JSON ARRAY
  (official contract) — parsing must accept it; no-match and ambiguity
  remain hard errors;
- double-chance outcome names are normalized from real official
  spellings (`Arsenal or Draw` etc.);
- `alternate_totals` supplies exact O/U 1.5/2.5 lines when the featured
  totals market omits them;
- internal fixture UUIDs never reach URLs; the exact outgoing path uses
  provider sport key + provider event id.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sports_intelligence.providers.errors import ProviderMappingError
from sports_intelligence.providers.odds.factory import TheOddsApiProvider

EVENT_ID = "abcdef123456"
SPORT_KEY = "soccer_epl"
INTERNAL_UUID_HINT = "11111111-2222-3333-4444-555555555555"

# Official contract: the events endpoint returns a bare top-level array.
EVENTS_PAYLOAD = [
    {
        "id": EVENT_ID,
        "sport_key": SPORT_KEY,
        "commence_time": "2026-08-21T14:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Coventry",
    }
]

ODDS_PAYLOAD = {
    "id": EVENT_ID,
    "sport_key": SPORT_KEY,
    "commence_time": "2026-08-21T14:00:00Z",
    "home_team": "Arsenal",
    "away_team": "Coventry",
    "last_update": "2026-08-21T10:00:00Z",
    "bookmakers": [
        {
            "key": "sportsbook",
            "title": "Sportsbook",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 2.10},
                        {"name": "Draw", "price": 3.40},
                        {"name": "Coventry", "price": 3.60},
                    ],
                },
                {
                    "key": "double_chance",
                    "outcomes": [
                        {"name": "Arsenal or Draw", "price": 1.30},
                        {"name": "Coventry or Draw", "price": 1.85},
                        {"name": "Arsenal or Coventry", "price": 1.25},
                    ],
                },
                {
                    "key": "alternate_totals",
                    "outcomes": [
                        {"name": "Over 1.5", "price": 1.60, "point": 1.5},
                        {"name": "Under 1.5", "price": 2.30, "point": 1.5},
                    ],
                },
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over 2.5", "price": 1.85, "point": 2.5},
                        {"name": "Under 2.5", "price": 1.95, "point": 2.5},
                    ],
                },
            ],
        }
    ],
}


def _make_transport(*, events: list | None = None) -> httpx.MockTransport:
    captured_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_paths.append(request.url.path)
        if "/events/" in request.url.path:
            return httpx.Response(200, json=ODDS_PAYLOAD)
        return httpx.Response(200, json=events if events is not None else EVENTS_PAYLOAD)

    transport = httpx.MockTransport(handler)
    transport.captured_paths = captured_paths  # type: ignore[attr-defined]
    return transport


def _provider(transport: httpx.MockTransport) -> TheOddsApiProvider:
    return TheOddsApiProvider(
        api_key="odds-key",
        base_url="https://api.example.test/v4",
        client=httpx.AsyncClient(transport=transport),
        max_attempts=1,
        backoff_seconds=0.001,
    )


@pytest.mark.asyncio
async def test_resolve_event_accepts_top_level_array_contract() -> None:
    """M4.2 §4: the events endpoint returns a bare JSON array."""
    transport = _make_transport()
    provider = _provider(transport)
    event_id = await provider.resolve_event(
        sport_key=SPORT_KEY,
        home_team="Arsenal",
        away_team="Coventry",
        commence_time_utc=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
    )
    assert event_id == EVENT_ID
    assert "/soccer_epl/events" in transport.captured_paths[0]
    assert INTERNAL_UUID_HINT not in transport.captured_paths[0]
    await provider.aclose()


@pytest.mark.asyncio
async def test_odds_path_uses_provider_event_id_not_internal_uuid() -> None:
    transport = _make_transport()
    provider = _provider(transport)
    result = await provider.fetch_event_odds(
        sport_key=SPORT_KEY,
        event_id=EVENT_ID,
        markets=["h2h"],
        regions=["eu"],
    )
    assert transport.captured_paths[0] == f"/v4/sports/{SPORT_KEY}/events/{EVENT_ID}/odds"
    assert INTERNAL_UUID_HINT not in transport.captured_paths[0]
    assert result.fixture_id == EVENT_ID
    assert result.prices
    await provider.aclose()


@pytest.mark.asyncio
async def test_resolve_event_no_match_is_hard_error() -> None:
    transport = _make_transport()
    provider = _provider(transport)
    with pytest.raises(ProviderMappingError):
        await provider.resolve_event(
            sport_key=SPORT_KEY,
            home_team="Nobody",
            away_team="Nowhere",
            commence_time_utc=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
        )
    await provider.aclose()


@pytest.mark.asyncio
async def test_resolve_event_ambiguous_is_hard_error_never_guessed() -> None:
    ambiguous = [
        {
            "id": "event-a",
            "sport_key": SPORT_KEY,
            "commence_time": "2026-08-21T14:00:00Z",
            "home_team": "Arsenal",
            "away_team": "Coventry",
        },
        {
            "id": "event-b",
            "sport_key": SPORT_KEY,
            "commence_time": "2026-08-21T14:00:00Z",
            "home_team": "Arsenal",
            "away_team": "Coventry",
        },
    ]
    transport = _make_transport(events=ambiguous)
    provider = _provider(transport)
    with pytest.raises(ProviderMappingError):
        await provider.resolve_event(
            sport_key=SPORT_KEY,
            home_team="Arsenal",
            away_team="Coventry",
            commence_time_utc=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
        )
    await provider.aclose()


@pytest.mark.asyncio
async def test_fetch_odds_normalizes_real_double_chance_and_alternate_totals() -> None:
    """M4.2 §5: real double-chance names (`Arsenal or Draw` …) map to
    canonical selections; alternate_totals supplies the exact 1.5 line
    the featured totals market omits."""
    transport = _make_transport()
    provider = _provider(transport)
    result = await provider.fetch_event_odds(
        sport_key=SPORT_KEY,
        event_id=EVENT_ID,
        markets=["h2h", "double_chance", "totals", "btts"],
        regions=["eu"],
    )
    by_market_selection = {(p.market, p.selection) for p in result.prices}
    # Real double-chance names → canonical selections.
    assert ("double_chance", "home_or_draw") in by_market_selection
    assert ("double_chance", "draw_or_away") in by_market_selection
    assert ("double_chance", "home_or_away") in by_market_selection
    # Featured totals (2.5) AND alternate_totals (1.5) both canonical.
    assert ("ou_15", "over") in by_market_selection
    assert ("ou_15", "under") in by_market_selection
    assert ("ou_25", "over") in by_market_selection
    assert ("ou_25", "under") in by_market_selection
    await provider.aclose()


@pytest.mark.asyncio
async def test_estimate_cost_credits_regions_times_markets() -> None:
    provider = _provider(_make_transport())
    assert provider.estimate_cost(markets=["h2h", "totals"], regions=["eu"]) == 2
    assert provider.estimate_cost(markets=["h2h", "totals"], regions=["eu", "uk"]) == 4
    await provider.aclose()


@pytest.mark.asyncio
async def test_fetch_odds_returns_rate_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ODDS_PAYLOAD,
            headers={
                "x-requests-remaining": "492",
                "x-requests-used": "8",
                "x-requests-last": "5",
            },
        )

    transport = httpx.MockTransport(handler)
    provider = _provider(transport)
    result = await provider.fetch_event_odds(
        sport_key=SPORT_KEY,
        event_id=EVENT_ID,
        markets=["h2h"],
        regions=["eu"],
    )
    assert result.rate_headers["x-requests-remaining"] == "492"
    assert result.rate_headers["x-requests-last"] == "5"
    await provider.aclose()
