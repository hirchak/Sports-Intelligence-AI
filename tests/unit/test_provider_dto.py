from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    ProviderFixture,
    ProviderLeague,
    ProviderResponseMetadata,
    ProviderSeason,
    ProviderTeam,
)

UTC = UTC


def _fixture_kwargs() -> dict[str, object]:
    return {
        "provider_fixture_id": 1,
        "provider_league_id": 39,
        "provider_season": 2026,
        "provider_home_team_id": 101,
        "provider_away_team_id": 102,
        "home_team_name": "Home FC",
        "away_team_name": "Away FC",
        "kickoff_utc": datetime(2026, 8, 21, 19, 0, tzinfo=UTC),
        "status_short": "NS",
        "provider": "api_football",
        "retrieved_at": datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    }


def test_provider_fixture_accepts_complete_data() -> None:
    fixture = ProviderFixture(**_fixture_kwargs())
    assert fixture.provider_league_id == 39
    assert fixture.home_team_name == "Home FC"
    assert fixture.status_short == "NS"


def test_provider_fixture_rejects_naive_kickoff() -> None:
    kwargs = _fixture_kwargs()
    kwargs["kickoff_utc"] = datetime(2026, 8, 21, 19, 0)
    with pytest.raises(ValidationError):
        ProviderFixture(**kwargs)


def test_provider_fixture_normalizes_offset_kickoff_to_utc() -> None:
    kwargs = _fixture_kwargs()
    kwargs["kickoff_utc"] = datetime(2026, 8, 21, 19, 0, tzinfo=timezone(timedelta(hours=2)))
    fixture = ProviderFixture(**kwargs)
    assert fixture.kickoff_utc == datetime(2026, 8, 21, 17, 0, tzinfo=UTC)


def test_provider_fixture_missing_optionals_stay_none() -> None:
    kwargs = _fixture_kwargs()
    kwargs.pop("provider_season")
    fixture = ProviderFixture(**kwargs)
    assert fixture.provider_season is None
    assert fixture.venue is None
    assert fixture.round is None
    assert fixture.status_long is None


def test_discovery_result_aggregates_entities() -> None:
    result = FixtureDiscoveryResult(
        metadata=ProviderResponseMetadata(
            provider="api_football",
            endpoint_family="fixtures_by_date",
            request_fingerprint="fixtures:date:2026-08-21",
            retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
        ),
        leagues=[ProviderLeague(provider_league_id=39, name="Premier League")],
        seasons=[ProviderSeason(provider_league_id=39, season=2026)],
        teams=[ProviderTeam(provider_team_id=1, name="Home FC")],
        fixtures=[ProviderFixture(**_fixture_kwargs())],
    )
    assert len(result.fixtures) == 1
    assert result.metadata.provider == "api_football"
