from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sports_intelligence.core.time import utc_now
from sports_intelligence.providers.base import ProviderCapabilities
from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    LineupPublicationState,
    PlayerAvailabilityEntry,
    ProviderAvailabilityResult,
    ProviderCompletedFixture,
    ProviderCompletedFixturesResult,
    ProviderLineupPlayer,
    ProviderLineupsResult,
    ProviderResponseMetadata,
    ProviderStandingRow,
    ProviderStandingsResult,
    ProviderTeamAvailability,
    ProviderTeamLineup,
    ProviderTeamStatisticsResult,
    canonical_request_fingerprint,
)
from sports_intelligence.providers.sports.api_football import parse_fixtures_response

DEFAULT_DATASET_PATH = Path(__file__).parent / "mock_data" / "fixtures_2026-08-21.json"

# Deterministic canned category payloads. Allowed ONLY in this mock
# provider; the real adapter never reads these constants.
MOCK_LEAGUE_ID = 39
MOCK_SEASON = 2026
MOCK_TEAM_HOME_ID = 9001
MOCK_TEAM_AWAY_ID = 9002
MOCK_FIXTURE_ID = 42


def _canned_standings() -> ProviderStandingsResult:
    return ProviderStandingsResult(
        provider="mock",
        retrieved_at=utc_now(),
        raw_payload={"response": [{"league": {"standings": []}}]},
        provider_league_id=MOCK_LEAGUE_ID,
        season=MOCK_SEASON,
        rows=[
            ProviderStandingRow(
                rank=1,
                provider_team_id=MOCK_TEAM_HOME_ID,
                team_name="Mock United",
                points=9,
                played=3,
                wins=3,
                draws=0,
                losses=0,
                goals_for=7,
                goals_against=1,
                form="WWW",
            ),
            ProviderStandingRow(
                rank=2,
                provider_team_id=MOCK_TEAM_AWAY_ID,
                team_name="Mock City",
                points=7,
                played=3,
                wins=2,
                draws=1,
                losses=0,
                goals_for=6,
                goals_against=2,
                form="WWD",
            ),
        ],
    )


def _canned_team_statistics(team_id: int) -> ProviderTeamStatisticsResult:
    return ProviderTeamStatisticsResult(
        provider="mock",
        retrieved_at=utc_now(),
        raw_payload={"response": []},
        provider_team_id=team_id,
        provider_league_id=MOCK_LEAGUE_ID,
        season=MOCK_SEASON,
        metrics={
            "form": "WWD",
            "played": 3,
            "wins": 2,
            "draws": 1,
            "losses": 0,
            "goals_for": 6,
            "goals_against": 2,
            "clean_sheets": 1,
            "failed_to_score": 0,
        },
    )


def _canned_availability() -> ProviderAvailabilityResult:
    return ProviderAvailabilityResult(
        provider="mock",
        retrieved_at=utc_now(),
        raw_payload={"response": []},
        provider_fixture_id=MOCK_FIXTURE_ID,
        teams=[
            ProviderTeamAvailability(
                provider_team_id=MOCK_TEAM_HOME_ID,
                team_name="Mock United",
                entries=[
                    PlayerAvailabilityEntry(
                        player_name="Mock Player A",
                        provider_player_id=101,
                        entry_type="Missing Fixture",
                        reason="Injury",
                        missing=True,
                    ),
                    PlayerAvailabilityEntry(
                        player_name="Mock Player B",
                        provider_player_id=102,
                        entry_type="Questionable",
                        reason="Knock",
                        missing=False,
                    ),
                ],
            ),
            ProviderTeamAvailability(
                provider_team_id=MOCK_TEAM_AWAY_ID,
                team_name="Mock City",
                entries=[],
            ),
        ],
    )


def _canned_lineups(*, published: bool = True) -> ProviderLineupsResult:

    if not published:
        return ProviderLineupsResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_fixture_id=MOCK_FIXTURE_ID,
            publication_state=LineupPublicationState.NOT_YET_PUBLISHED,
            teams=[],
        )
    starters_home = [
        ProviderLineupPlayer(
            player_name=f"Mock Starter {i}",
            provider_player_id=200 + i,
            shirt_number=i,
            position="MF",
            starter=True,
        )
        for i in range(1, 12)
    ]
    return ProviderLineupsResult(
        provider="mock",
        retrieved_at=utc_now(),
        raw_payload={"response": [{"team": {}, "startXI": []}]},
        provider_fixture_id=MOCK_FIXTURE_ID,
        publication_state=LineupPublicationState.CONFIRMED,
        teams=[
            ProviderTeamLineup(
                provider_team_id=MOCK_TEAM_HOME_ID,
                team_name="Mock United",
                formation="4-3-3",
                confirmed=True,
                starters=starters_home,
                substitutes=[],
            ),
            ProviderTeamLineup(
                provider_team_id=MOCK_TEAM_AWAY_ID,
                team_name="Mock City",
                formation="4-4-2",
                confirmed=True,
                starters=[
                    ProviderLineupPlayer(
                        player_name=f"Mock Away Starter {i}",
                        provider_player_id=300 + i,
                        shirt_number=i,
                        position="DF",
                        starter=True,
                    )
                    for i in range(1, 12)
                ],
                substitutes=[],
            ),
        ],
    )


def _canned_completed_fixtures(team_id: int) -> ProviderCompletedFixturesResult:
    now = utc_now()
    fixtures: list[ProviderCompletedFixture] = []
    outcomes = [
        ("W", 2, 0),
        ("W", 3, 1),
        ("D", 1, 1),
        ("L", 0, 2),
        ("W", 2, 1),
        ("D", 0, 0),
        ("W", 1, 0),
        ("L", 1, 3),
        ("W", 2, 1),
        ("W", 4, 0),
    ]
    for idx, (label, gf, ga) in enumerate(outcomes):
        kickoff = now - timedelta(days=7 * (idx + 1))
        home_id, away_id = (team_id, 8000 + idx) if label != "L" else (8000 + idx, team_id)
        fixtures.append(
            ProviderCompletedFixture(
                provider_fixture_id=5000 + idx,
                kickoff_utc=kickoff,
                provider_home_team_id=home_id,
                provider_away_team_id=away_id,
                home_goals=gf if home_id == team_id else ga,
                away_goals=ga if home_id == team_id else gf,
                status_short="FT",
            )
        )
    return ProviderCompletedFixturesResult(
        provider="mock",
        retrieved_at=utc_now(),
        raw_payload={"response": []},
        provider_team_id=team_id,
        fixtures=fixtures,
    )


class MockSportsDataProvider:
    def __init__(
        self,
        responses: dict[str, dict[str, object]] | None = None,
        provider_name: str = "mock",
        *,
        lineups_published: bool = True,
    ) -> None:
        self._responses = responses
        self._provider_name = provider_name
        self._builtin: dict[str, object] | None = None
        self._lineups_published = lineups_published

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self._provider_name,
            supports_fixtures_by_date=True,
            supports_standings=True,
            supports_team_statistics=True,
            supports_availability=True,
            supports_lineups=True,
            supports_completed_fixtures=True,
        )

    async def get_fixtures_by_date(
        self, fixture_date: date, timezone_name: str | None = None
    ) -> FixtureDiscoveryResult:
        iso = fixture_date.isoformat()
        params = {"date": iso}
        if timezone_name is not None:
            params["timezone"] = timezone_name
        retrieved_at = utc_now()
        payload = self._load(iso)
        fingerprint = canonical_request_fingerprint(self._provider_name, "fixtures_by_date", params)
        if payload is None:
            return FixtureDiscoveryResult(
                metadata=ProviderResponseMetadata(
                    provider=self._provider_name,
                    endpoint_family="fixtures_by_date",
                    request_fingerprint=fingerprint,
                    retrieved_at=retrieved_at,
                    results_count=0,
                ),
            )
        result = parse_fixtures_response(
            payload, retrieved_at=retrieved_at, provider=self._provider_name
        )
        result.metadata.request_fingerprint = fingerprint
        return result

    async def get_standings(
        self, *, provider_league_id: int, season: int | None
    ) -> ProviderStandingsResult:
        canned = _canned_standings()
        return canned.model_copy(
            update={
                "provider": self._provider_name,
                "provider_league_id": provider_league_id,
                "season": season,
            }
        )

    async def get_team_statistics(
        self, *, provider_team_id: int, provider_league_id: int, season: int | None
    ) -> ProviderTeamStatisticsResult:
        canned = _canned_team_statistics(provider_team_id)
        return canned.model_copy(
            update={
                "provider": self._provider_name,
                "provider_league_id": provider_league_id,
                "season": season,
            }
        )

    async def get_availability(self, *, provider_fixture_id: int) -> ProviderAvailabilityResult:
        canned = _canned_availability()
        return canned.model_copy(
            update={"provider": self._provider_name, "provider_fixture_id": provider_fixture_id}
        )

    async def get_lineups(self, *, provider_fixture_id: int) -> ProviderLineupsResult:
        canned = _canned_lineups(published=self._lineups_published)
        return canned.model_copy(
            update={"provider": self._provider_name, "provider_fixture_id": provider_fixture_id}
        )

    async def get_completed_fixtures(
        self, *, provider_team_id: int, last_n: int
    ) -> ProviderCompletedFixturesResult:
        canned = _canned_completed_fixtures(provider_team_id)
        return canned.model_copy(
            update={
                "provider": self._provider_name,
                "provider_team_id": provider_team_id,
                "fixtures": canned.fixtures[: max(min(last_n, 20), 0)],
            }
        )

    async def aclose(self) -> None:
        return None

    def _load(self, iso: str) -> dict[str, object] | None:
        if self._responses is not None:
            return self._responses.get(iso)
        if self._builtin is None:
            self._builtin = json.loads(DEFAULT_DATASET_PATH.read_text())
        if iso in _DEFAULT_DATASET_DATES:
            return self._builtin
        return None


_DEFAULT_DATASET_DATES = frozenset({"2026-08-21"})
