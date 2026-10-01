from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from sports_intelligence.evaluation.settlement import ResultObservation


def canonical_request_fingerprint(
    provider: str, endpoint_family: str, params: Mapping[str, str]
) -> str:
    normalized = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return f"{provider}:{endpoint_family}:{normalized}"


class ProviderResponseMetadata(BaseModel):
    provider: str
    endpoint_family: str
    request_fingerprint: str
    retrieved_at: datetime
    results_count: int | None = None
    rate_limit_remaining: int | None = None
    """Relevant rate-limit headers exactly as sent by the provider."""
    rate_headers: dict[str, str] = Field(default_factory=dict)


class ProviderLeague(BaseModel):
    provider_league_id: int
    name: str | None = None
    country: str | None = None


class ProviderSeason(BaseModel):
    provider_league_id: int
    season: int


class ProviderTeam(BaseModel):
    provider_team_id: int
    name: str | None = None


class ProviderFixture(BaseModel):
    provider_fixture_id: int
    provider_league_id: int
    provider_season: int | None = None
    provider_home_team_id: int
    provider_away_team_id: int
    home_team_name: str | None = None
    away_team_name: str | None = None
    kickoff_utc: datetime
    venue: str | None = None
    round: str | None = None
    status_short: str
    status_long: str | None = None
    retrieved_at: datetime
    provider: str

    @field_validator("kickoff_utc")
    @classmethod
    def normalize_kickoff_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("retrieved_at")
    @classmethod
    def normalize_retrieved_at_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value.astimezone(UTC)


class FixtureDiscoveryResult(BaseModel):
    metadata: ProviderResponseMetadata
    leagues: list[ProviderLeague] = Field(default_factory=list)
    seasons: list[ProviderSeason] = Field(default_factory=list)
    teams: list[ProviderTeam] = Field(default_factory=list)
    fixtures: list[ProviderFixture] = Field(default_factory=list)
    raw_payload: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# M4 category DTOs — typed provider surface for collectors. Every result
# carries provider identity, retrieval time, the raw response payload and
# the rate-limit headers so evidence/ledger stay traceable end-to-end.
# ---------------------------------------------------------------------------


class _CategoryResultBase(BaseModel):
    provider: str
    retrieved_at: datetime
    rate_headers: dict[str, str] = Field(default_factory=dict)
    raw_payload: dict[str, Any]

    @field_validator("retrieved_at")
    @classmethod
    def normalize_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value.astimezone(UTC)


class ProviderStandingRow(BaseModel):
    rank: int | None = None
    provider_team_id: int
    team_name: str | None = None
    points: int | None = None
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    form: str | None = None


class ProviderStandingsResult(_CategoryResultBase):
    provider_league_id: int
    season: int | None = None
    rows: list[ProviderStandingRow] = Field(default_factory=list)


class ProviderTeamStatisticsResult(_CategoryResultBase):
    provider_team_id: int
    provider_league_id: int
    season: int | None = None
    metrics: dict[str, Any]


class PlayerAvailabilityEntry(BaseModel):
    player_name: str | None = None
    provider_player_id: int | None = None
    entry_type: str | None = None  # injury / suspension / doubt ...
    reason: str | None = None
    missing: bool  # True → expected NOT to play; False → doubtful/other


class ProviderTeamAvailability(BaseModel):
    """Availability entries bound to ONE team (never merged across sides)."""

    provider_team_id: int
    team_name: str | None = None
    entries: list[PlayerAvailabilityEntry] = Field(default_factory=list)


class ProviderAvailabilityResult(_CategoryResultBase):
    """One provider request per fixture covering BOTH teams."""

    provider_fixture_id: int
    teams: list[ProviderTeamAvailability] = Field(default_factory=list)


class ProviderLineupPlayer(BaseModel):
    player_name: str | None = None
    provider_player_id: int | None = None
    shirt_number: int | None = None
    position: str | None = None
    starter: bool


class ProviderTeamLineup(BaseModel):
    provider_team_id: int
    team_name: str | None = None
    formation: str | None = None
    confirmed: bool
    starters: list[ProviderLineupPlayer] = Field(default_factory=list)
    substitutes: list[ProviderLineupPlayer] = Field(default_factory=list)


class LineupPublicationState(StrEnum):
    NOT_YET_PUBLISHED = "NOT_YET_PUBLISHED"
    CONFIRMED = "CONFIRMED"
    UNSUPPORTED = "UNSUPPORTED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class ProviderLineupsResult(_CategoryResultBase):
    """One provider request per fixture covering BOTH teams."""

    provider_fixture_id: int
    publication_state: LineupPublicationState
    teams: list[ProviderTeamLineup] = Field(default_factory=list)


class ProviderCompletedFixture(BaseModel):
    provider_fixture_id: int
    kickoff_utc: datetime
    provider_home_team_id: int
    provider_away_team_id: int
    home_goals: int | None = None
    away_goals: int | None = None
    status_short: str

    @field_validator("kickoff_utc")
    @classmethod
    def normalize_kickoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        return value.astimezone(UTC)


class ProviderCompletedFixturesResult(_CategoryResultBase):
    """Recent completed results for ONE team — deterministic form inputs."""

    provider_team_id: int
    fixtures: list[ProviderCompletedFixture] = Field(default_factory=list)


class ProviderResultsBatch(_CategoryResultBase):
    """One single physical request; retries and quota owned by M8 collector."""

    results: list[ResultObservation]
