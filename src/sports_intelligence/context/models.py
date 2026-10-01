from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FixtureIdentitySection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str
    league_id: str
    season_id: str | None = None
    home_team_id: str
    away_team_id: str
    kickoff_at: str
    venue: str | None = None
    round: str | None = None
    status: str
    league_slug: str | None = None
    league_name: str | None = None
    home_team_name: str | None = None
    away_team_name: str | None = None
    fixture_metadata_snapshot_id: str | None = None
    metadata_captured_at: str | None = None
    home_provider_mappings: list[dict[str, Any]] = Field(default_factory=list)
    away_provider_mappings: list[dict[str, Any]] = Field(default_factory=list)


class TeamFormSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    home_sample_size: int | None = None
    away_sample_size: int | None = None
    home_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    away_outcomes: list[dict[str, Any]] = Field(default_factory=list)


class HomeAwayContextSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    home_split_ppg: float | None = None
    away_split_ppg: float | None = None


class SeasonStrengthSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
    model_config = ConfigDict(extra="forbid", frozen=True)

    home_days_since_last_match: float | None = None
    away_days_since_last_match: float | None = None
    rest_days_delta: float | None = None
    home_matches_last_7d: int | None = None
    away_matches_last_7d: int | None = None
    home_matches_last_14d: int | None = None
    away_matches_last_14d: int | None = None
    fixture_congestion_delta: int | None = None


class AvailabilitySection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    home_state: str | None = None
    away_state: str | None = None
    home_missing_count: int | None = None
    away_missing_count: int | None = None
    home_players: list[dict[str, Any]] = Field(default_factory=list)
    away_players: list[dict[str, Any]] = Field(default_factory=list)
    home_conflicts: int | None = None
    away_conflicts: int | None = None


class LineupsSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool = False
    reason: str | None = None
    matches: list[dict[str, Any]] = Field(default_factory=list)


class ResearchClaimSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    url: str
    domain: str
    title: str
    published_at: str | None = None
    retrieved_at: str | None = None
    content_hash: str
    provider: str


class ResearchClaimItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
    source: ResearchClaimSource | None = None


class ResearchClaimsSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    run_id: str | None = None
    provider: str | None = None
    documents_count: int = 0
    claims_count: int = 0
    conflicts_count: int = 0
    claims: list[ResearchClaimItem] = Field(default_factory=list)


class MarketPriceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market: str
    selection: str
    decimal_odds: float
    implied_probability: float
    no_vig_probability: float | None = None
    bookmaker: str | None = None
    line: float | None = None


class MarketSnapshotSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_odds: bool
    bookmakers: list[str] = Field(default_factory=list)
    captured_at: str | None = None
    prices: list[MarketPriceItem] = Field(default_factory=list)
    movement: dict[str, float | None] = Field(default_factory=dict)


class DeterministicFeaturesSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "features_v1"

    # Form (Last 5 & Last 10)
    home_last5_ppg: float | None = None
    away_last5_ppg: float | None = None
    home_last10_ppg: float | None = None
    away_last10_ppg: float | None = None
    home_last10_goals_for_per_match: float | None = None
    away_last10_goals_for_per_match: float | None = None
    home_last10_goals_against_per_match: float | None = None
    away_last10_goals_against_per_match: float | None = None
    home_last5_goals_for_per_match: float | None = None
    away_last5_goals_for_per_match: float | None = None
    home_last5_goals_against_per_match: float | None = None
    away_last5_goals_against_per_match: float | None = None
    home_home_split_ppg: float | None = None
    away_away_split_ppg: float | None = None
    home_scored_rate: float | None = None
    away_scored_rate: float | None = None
    home_conceded_rate: float | None = None
    away_conceded_rate: float | None = None
    home_clean_sheet_rate: float | None = None
    away_clean_sheet_rate: float | None = None
    home_sample_size: int | None = None
    away_sample_size: int | None = None

    # Schedule / Fatigue
    home_days_since_last_match: float | None = None
    away_days_since_last_match: float | None = None
    rest_days_delta: float | None = None
    home_matches_last_7d: int | None = None
    away_matches_last_7d: int | None = None
    home_matches_last_14d: int | None = None
    away_matches_last_14d: int | None = None
    fixture_congestion_delta: int | None = None

    # Standings / Season Strength
    home_league_position: int | None = None
    away_league_position: int | None = None
    league_position_delta: int | None = None
    home_season_points_per_game: float | None = None
    away_season_points_per_game: float | None = None
    home_season_goals_for_per_game: float | None = None
    away_season_goals_for_per_game: float | None = None
    home_season_goals_against_per_game: float | None = None
    away_season_goals_against_per_game: float | None = None

    # Availability
    home_missing_players_count: int | None = None
    away_missing_players_count: int | None = None
    home_availability_state: str | None = None
    away_availability_state: str | None = None
    home_availability_conflict_count: int | None = None
    away_availability_conflict_count: int | None = None
    important_absence_delta: float | None = None
    top_scorer_missing: bool | None = None
    starting_goalkeeper_missing: bool | None = None
    multiple_starting_defenders_missing: bool | None = None

    # Lineups
    home_lineup_confirmed: bool | None = None
    away_lineup_confirmed: bool | None = None
    lineups_both_confirmed: bool | None = None
    home_lineup_formation: str | None = None
    away_lineup_formation: str | None = None
    home_lineup_publication_state: str | None = None
    away_lineup_publication_state: str | None = None

    # Market (No-vig)
    market_home_no_vig: float | None = None
    market_draw_no_vig: float | None = None
    market_away_no_vig: float | None = None
    market_over15_no_vig: float | None = None
    market_under15_no_vig: float | None = None
    market_over25_no_vig: float | None = None
    market_under25_no_vig: float | None = None
    market_btts_yes_no_vig: float | None = None
    market_btts_no_no_vig: float | None = None

    # Odds Movement
    odds_move_home: float | None = None
    odds_move_over25: float | None = None

    # Diagnostics
    missing_features: dict[str, str] = Field(default_factory=dict)


class DataQualitySection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    forecast_phase: str
    as_of: str
    overall_score: float
    quality_band: str
    can_predict: bool
    dimension_scores: dict[str, float]
    critical_missing: list[str]
    missing_fields: list[dict[str, Any]]
    warnings: list[str]
    conflicts: list[dict[str, Any]]
    provider_errors: list[dict[str, Any]]
    stale_sources: list[str]
    source_manifest: SourceManifestSection
    source_fingerprint: str | None = None
    quality_policy: dict[str, Any] = Field(default_factory=dict)
    policy_fingerprint: str | None = None
    freshness_policy: dict[str, Any] = Field(default_factory=dict)
    freshness_policy_fingerprint: str | None = None


class ProvenanceRecordSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str
    table: str
    snapshot_id: str | None = None
    provider: str | None = None
    captured_at: str | None = None
    payload_id: str | None = None
    fingerprint: str | None = None
    details: dict[str, Any] | None = None


class SourceManifestSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_fingerprint: str
    sources: dict[str, ProvenanceRecordSection]


class MatchContextV1(BaseModel):
    """Immutable, strictly typed MatchContext V1 data structure.

    Sections strictly ordered 1 through 13 per specification.
    Contains ONLY point-in-time facts available at or before `as_of`.
    Zero future leakage, zero prediction probabilities, zero LLM text.
    Strict extra='forbid' validation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identity
    schema_version: str
    fixture_id: str
    forecast_phase: str
    as_of: str

    # Sections 1–13
    fixture_identity: FixtureIdentitySection
    team_form: TeamFormSection
    home_away_context: HomeAwayContextSection
    season_strength: SeasonStrengthSection
    schedule_fatigue: ScheduleFatigueSection
    availability: AvailabilitySection
    lineups: LineupsSection
    head_to_head: HeadToHeadSection
    research_claims: ResearchClaimsSection
    market_snapshot: MarketSnapshotSection
    deterministic_features: DeterministicFeaturesSection
    data_quality: DataQualitySection
    source_manifest: SourceManifestSection

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def canonical_json(self) -> str:
        """Deterministic canonical JSON serialization for stable cryptographic hashing."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
