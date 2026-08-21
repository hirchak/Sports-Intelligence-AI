from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
