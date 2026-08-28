"""M4.1 §2 sentinel regression: ApiFootballProvider NEVER returns MOCK data.

A real-style API-Football adapter configured with a MockTransport
returning DISTINCTIVE sentinel values must, when run through the
collectors, persist EXACTLY those provider values — the canned
Arsenal/Coventry/Mock United payloads must never appear.
"""

from __future__ import annotations

import httpx
import pytest

from sports_intelligence.providers.sports.api_football import ApiFootballProvider

SENTINEL_LEAGUE = 12345
SENTINEL_SEASON = 2026
SENTINEL_TEAM_HOME = 77701
SENTINEL_TEAM_AWAY = 77702
SENTINEL_FIXTURE = 88801

SENTINEL_STANDINGS = {
    "response": [
        {
            "league": {
                "id": SENTINEL_LEAGUE,
                "season": SENTINEL_SEASON,
                "standings": [
                    [
                        {
                            "rank": 1,
                            "team": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
                            "points": 30,
                            "all": {
                                "played": 10,
                                "win": 9,
                                "draw": 0,
                                "lose": 1,
                                "goals": {"for": 28, "against": 5},
                            },
                            "form": "WWWWL",
                        },
                        {
                            "rank": 2,
                            "team": {"id": SENTINEL_TEAM_AWAY, "name": "Sentinel City"},
                            "points": 24,
                            "all": {
                                "played": 10,
                                "win": 7,
                                "draw": 1,
                                "lose": 2,
                                "goals": {"for": 20, "against": 9},
                            },
                            "form": "WWDLW",
                        },
                    ]
                ],
            }
        }
    ]
}

SENTINEL_INJURIES = {
    "response": [
        {
            "team": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
            "player": {"id": 5001, "name": "Sentinel Missing Star"},
            "type": "Missing Fixture",
            "reason": "Injury",
        },
        {
            "team": {"id": SENTINEL_TEAM_AWAY, "name": "Sentinel City"},
            "player": {"id": 5002, "name": "Sentinel Doubtful"},
            "type": "Questionable",
            "reason": "Knock",
        },
    ]
}

SENTINEL_LINEUPS = {
    "response": [
        {
            "team": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
            "formation": "4-2-3-1",
            "startXI": [{"player": {"id": 6001, "name": "Sentinel GK", "number": 1, "pos": "G"}}],
            "substitutes": [],
        },
        {
            "team": {"id": SENTINEL_TEAM_AWAY, "name": "Sentinel City"},
            "formation": "4-4-2",
            "startXI": [{"player": {"id": 6002, "name": "Sentinel DF", "number": 4, "pos": "D"}}],
            "substitutes": [],
        },
    ]
}

SENTINEL_TEAM_STATS = {
    "get": "teams/statistics",
    "parameters": {"team": str(SENTINEL_TEAM_HOME), "league": str(SENTINEL_LEAGUE)},
    "response": {
        "team": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
        "league": {"id": SENTINEL_LEAGUE, "season": SENTINEL_SEASON},
        "fixtures": {
            "played": {"home": 5, "away": 5, "total": 10},
            "wins": {"home": 5, "away": 4, "total": 9},
            "draws": {"home": 0, "away": 1, "total": 1},
            "loses": {"home": 0, "away": 0, "total": 0},
        },
        "goals": {
            "for": {"total": {"home": 15, "away": 13, "total": 28}},
            "against": {"total": {"home": 2, "away": 3, "total": 5}},
        },
        "clean_sheet": {"home": 3, "away": 1, "total": 4},
        "failed_to_score": {"home": 0, "away": 1, "total": 1},
        "form": "WWWWL",
    },
}

SENTINEL_COMPLETED = {
    "response": [
        {
            "fixture": {
                "id": 9001,
                "date": "2026-08-01T14:00:00+00:00",
                "status": {"short": "FT"},
            },
            "teams": {
                "home": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
                "away": {"id": 9099, "name": "Sentinel Rivals"},
            },
            "score": {"fulltime": {"home": 3, "away": 1}},
        },
        {
            "fixture": {
                "id": 9002,
                "date": "2026-08-08T14:00:00+00:00",
                "status": {"short": "FT"},
            },
            "teams": {
                "home": {"id": 9098, "name": "Sentinel Other"},
                "away": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
            },
            "score": {"fulltime": {"home": 0, "away": 2}},
        },
    ]
}


def _make_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/standings"):
            return httpx.Response(200, json=SENTINEL_STANDINGS)
        if request.url.path.endswith("/injuries"):
            return httpx.Response(200, json=SENTINEL_INJURIES)
        if request.url.path.endswith("/fixtures/lineups"):
            return httpx.Response(200, json=SENTINEL_LINEUPS)
        if request.url.path.endswith("/teams/statistics"):
            return httpx.Response(200, json=SENTINEL_TEAM_STATS)
        if request.url.path.endswith("/fixtures"):
            return httpx.Response(200, json=SENTINEL_COMPLETED)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def _provider() -> ApiFootballProvider:
    return ApiFootballProvider(
        api_key="sentinel-key",
        base_url="https://example.test/v3",
        client=httpx.AsyncClient(transport=_make_transport()),
        max_attempts=1,
        backoff_seconds=0.001,
    )


@pytest.mark.asyncio
async def test_standings_adapter_returns_only_sentinel_values() -> None:
    provider = _provider()
    result = await provider.get_standings(
        provider_league_id=SENTINEL_LEAGUE, season=SENTINEL_SEASON
    )
    assert result.provider == "api_football"
    names = {row.team_name for row in result.rows}
    assert names == {"Sentinel United", "Sentinel City"}
    assert "Arsenal" not in names
    assert "Mock United" not in names
    assert "Coventry" not in names
    await provider.aclose()


@pytest.mark.asyncio
async def test_availability_adapter_returns_sentinel_per_team() -> None:
    provider = _provider()
    result = await provider.get_availability(provider_fixture_id=SENTINEL_FIXTURE)
    assert result.provider == "api_football"
    by_team = {t.provider_team_id: t for t in result.teams}
    assert SENTINEL_TEAM_HOME in by_team
    assert SENTINEL_TEAM_AWAY in by_team
    assert by_team[SENTINEL_TEAM_HOME].entries[0].player_name == "Sentinel Missing Star"
    # No canned Arsenal/Coventry anywhere.
    assert all("Mock" not in (e.player_name or "") for t in result.teams for e in t.entries)
    await provider.aclose()


@pytest.mark.asyncio
async def test_lineups_adapter_returns_sentinel_formation_and_state() -> None:
    provider = _provider()
    result = await provider.get_lineups(provider_fixture_id=SENTINEL_FIXTURE)
    assert result.provider == "api_football"
    assert result.publication_state.value == "CONFIRMED"
    home = next(t for t in result.teams if t.provider_team_id == SENTINEL_TEAM_HOME)
    assert home.formation == "4-2-3-1"
    assert home.starters[0].player_name == "Sentinel GK"
    await provider.aclose()


@pytest.mark.asyncio
async def test_team_statistics_adapter_returns_sentinel_metrics() -> None:
    provider = _provider()
    result = await provider.get_team_statistics(
        provider_team_id=SENTINEL_TEAM_HOME,
        provider_league_id=SENTINEL_LEAGUE,
        season=SENTINEL_SEASON,
    )
    # M4.4 §1: every normalized metric from the contract-faithful shape.
    assert result.metrics["form"] == "WWWWL"
    assert result.metrics["played"] == 10
    assert result.metrics["wins"] == 9
    assert result.metrics["draws"] == 1
    # API-Football spells the key `loses`; normalized to `losses`.
    assert result.metrics["losses"] == 0
    # goals.for.total.{home,away,total} nested extraction.
    assert result.metrics["goals_for"] == 28
    assert result.metrics["goals_against"] == 5
    assert result.metrics["clean_sheets"] == 4
    assert result.metrics["failed_to_score"] == 1
    await provider.aclose()


@pytest.mark.asyncio
async def test_team_statistics_missing_values_remain_none() -> None:
    """M4.4 §1: missing provider values stay None — never fabricated
    zero."""
    payload = {
        "response": {
            "team": {"id": SENTINEL_TEAM_HOME, "name": "Sentinel United"},
            "league": {"id": SENTINEL_LEAGUE, "season": SENTINEL_SEASON},
            "fixtures": {"played": {"home": 2, "away": 2, "total": 4}},
            "goals": {},
        }
    }
    from sports_intelligence.core.time import utc_now
    from sports_intelligence.providers.sports.api_football import (
        parse_team_statistics_response,
    )

    result = parse_team_statistics_response(
        payload,
        provider_team_id=SENTINEL_TEAM_HOME,
        provider_league_id=SENTINEL_LEAGUE,
        season=SENTINEL_SEASON,
        retrieved_at=utc_now(),
    )
    assert result.metrics["played"] == 4
    assert result.metrics["wins"] is None
    assert result.metrics["losses"] is None
    assert result.metrics["goals_for"] is None
    assert result.metrics["goals_against"] is None
    assert result.metrics["clean_sheets"] is None
    assert result.metrics["failed_to_score"] is None


@pytest.mark.asyncio
async def test_completed_fixtures_adapter_returns_sentinel_results() -> None:
    provider = _provider()
    result = await provider.get_completed_fixtures(provider_team_id=SENTINEL_TEAM_HOME, last_n=5)
    assert len(result.fixtures) == 2
    assert result.fixtures[0].home_goals == 3
    assert result.fixtures[0].away_goals == 1
    assert result.fixtures[0].status_short == "FT"
    await provider.aclose()
