from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field


def _to_plain_dict(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dataclass_fields__"):
        return _to_plain_dict(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(item) for item in obj]
    return obj


class FixtureIdentitySection(BaseModel):
    model_config = ConfigDict(extra="allow")

    fixture_id: str
    league_id: str
    season_id: str | None = None
    home_team_id: str
    away_team_id: str
    kickoff_at: str
    venue: str | None = None
    round: str | None = None
    status: str
    league_slug: str
    league_name: str
    home_team_name: str | None = None
    away_team_name: str | None = None
    home_external_id: str | None = None
    away_external_id: str | None = None
    fixture_metadata_snapshot_id: str | None = None
    metadata_captured_at: str | None = None


class TeamFormSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_sample_size: int | None = None
    away_sample_size: int | None = None
    home_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    away_outcomes: list[dict[str, Any]] = Field(default_factory=list)


class HomeAwayContextSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_split_ppg: float | None = None
    away_split_ppg: float | None = None


class SeasonStrengthSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_league_position: int | None = None
    away_league_position: int | None = None
    league_position_delta: int | None = None
    home_season_points_per_game: float | None = None
    away_season_points_per_game: float | None = None
    home_season_goals_for_per_game: float | None = None
    away_season_goals_for_per_game: float | None = None
    home_season_goals_against_per_game: float | None = None
    away_season_goals_against_per_game: float | None = None


class ScheduleFatigueSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_days_since_last_match: float | None = None
    away_days_since_last_match: float | None = None
    rest_days_delta: float | None = None
    home_matches_last_7d: int | None = None
    away_matches_last_7d: int | None = None
    home_matches_last_14d: int | None = None
    away_matches_last_14d: int | None = None
    fixture_congestion_delta: int | None = None


class AvailabilitySection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_state: str | None = None
    away_state: str | None = None
    home_missing_count: int | None = None
    away_missing_count: int | None = None
    home_players: list[dict[str, Any]] = Field(default_factory=list)
    away_players: list[dict[str, Any]] = Field(default_factory=list)
    home_conflicts: int | None = None
    away_conflicts: int | None = None


class LineupsSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    home_confirmed: bool | None = None
    away_confirmed: bool | None = None
    lineups_both_confirmed: bool | None = None
    home_formation: str | None = None
    away_formation: str | None = None
    home_publication_state: str | None = None
    away_publication_state: str | None = None
    home_players: list[dict[str, Any]] = Field(default_factory=list)
    away_players: list[dict[str, Any]] = Field(default_factory=list)


class HeadToHeadSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool = False
    reason: str | None = None
    matches: list[dict[str, Any]] = Field(default_factory=list)


class ResearchClaimItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    document_id: str | None = None
    claim_type: str
    claim_text: str
    confidence: float
    team_id: str | None = None
    conflict_flag: bool = False
    conflicting_claim_id: str | None = None
    extracted_at: str
    source_reference: str | None = None


class ResearchClaimsSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    run_id: str | None = None
    provider: str | None = None
    documents_count: int = 0
    claims_count: int = 0
    conflicts_count: int = 0
    claims: list[ResearchClaimItem] = Field(default_factory=list)


class MarketPriceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: str
    selection: str
    decimal_odds: float
    implied_probability: float
    no_vig_probability: float | None = None
    bookmaker: str | None = None


class MarketSnapshotSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    has_odds: bool
    bookmaker: str | None = None
    captured_at: str | None = None
    prices: list[MarketPriceItem] = Field(default_factory=list)
    movement: dict[str, float | None] = Field(default_factory=dict)


@dataclass(frozen=True)
class MatchContextV1:
    """Immutable, typed MatchContext V1 data structure.

    Sections strictly ordered 1 through 13 per specification.
    Contains ONLY point-in-time facts available at or before `as_of`.
    Zero future leakage, zero prediction probabilities, zero LLM text.
    """

    # Identity
    schema_version: str
    fixture_id: str
    forecast_phase: str
    as_of: str

    # Sections 1–13
    fixture_identity: dict[str, Any]
    team_form: dict[str, Any]
    home_away_context: dict[str, Any]
    season_strength: dict[str, Any]
    schedule_fatigue: dict[str, Any]
    availability: dict[str, Any]
    lineups: dict[str, Any]
    head_to_head: dict[str, Any]
    research_claims: dict[str, Any]
    market_snapshot: dict[str, Any]
    deterministic_features: dict[str, Any]
    data_quality: dict[str, Any]
    source_manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], _to_plain_dict(asdict(self)))

    def canonical_json(self) -> str:
        """Deterministic canonical JSON serialization for stable cryptographic hashing."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
