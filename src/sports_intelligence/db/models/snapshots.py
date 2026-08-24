from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sports_intelligence.db.models.base import Base


class StandingSnapshot(Base):
    __tablename__ = "standings_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "league_id",
            "season_id",
            "captured_at",
            name="uq_standings_provider_league_season_captured",
        ),
        Index(
            "ix_standings_snapshots_league_captured",
            "league_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
        nullable=True,
    )
    rows_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TeamStatisticsSnapshot(Base):
    __tablename__ = "team_statistics_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "team_id",
            "league_id",
            "season_id",
            "captured_at",
            name="uq_team_stats_provider_team_league_season_captured",
        ),
        Index(
            "ix_team_statistics_snapshots_team_captured",
            "team_id",
            text("captured_at DESC"),
        ),
        Index(
            "ix_team_statistics_snapshots_league_captured",
            "league_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
        nullable=True,
    )
    metrics_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TeamFormSnapshot(Base):
    __tablename__ = "team_form_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "as_of",
            "window_size",
            "scope",
            name="uq_team_form_team_asof_window_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_size: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    metrics_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)


class AvailabilitySnapshot(Base):
    __tablename__ = "availability_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "fixture_id",
            "team_id",
            "captured_at",
            name="uq_availability_provider_fixture_team_captured",
        ),
        Index(
            "ix_availability_snapshots_fixture_team_captured",
            "fixture_id",
            "team_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
        nullable=True,
    )
    players_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    impact_flags_jsonb: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    conflicts_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    availability_state: Mapped[str] = mapped_column(String(16), nullable=False)


class LineupSnapshot(Base):
    __tablename__ = "lineup_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "fixture_id",
            "team_id",
            "captured_at",
            name="uq_lineups_provider_fixture_team_captured",
        ),
        Index(
            "ix_lineup_snapshots_fixture_team_captured",
            "fixture_id",
            "team_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    formation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    players_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # NOT_YET_PUBLISHED / CONFIRMED / UNSUPPORTED / PROVIDER_ERROR —
    # absence of a lineup is never an empty confirmed lineup.
    publication_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'NOT_YET_PUBLISHED'")
    )


class OddsSnapshotSet(Base):
    __tablename__ = "odds_snapshot_sets"
    __table_args__ = (
        Index(
            "ix_odds_snapshot_sets_fixture_captured",
            "fixture_id",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_whitelist_jsonb: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
        nullable=True,
    )


class OddsPrice(Base):
    __tablename__ = "odds_prices"
    __table_args__ = (
        CheckConstraint("decimal_odds > 1.0", name="ck_odds_prices_decimal_gt_one"),
        Index(
            "ix_odds_prices_snapshot_market",
            "snapshot_set_id",
            "market",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("odds_snapshot_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    bookmaker: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=2), nullable=True)
    decimal_odds: Mapped[float] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    implied_probability: Mapped[float] = mapped_column(
        Numeric(precision=8, scale=6), nullable=False
    )
    no_vig_probability: Mapped[float | None] = mapped_column(
        Numeric(precision=8, scale=6), nullable=True
    )


class ExternalApiRequest(Base):
    __tablename__ = "external_api_requests"
    __table_args__ = (
        Index(
            "ix_external_api_requests_provider_started",
            "provider",
            text("started_at DESC"),
        ),
        Index(
            "ix_external_api_requests_category_started",
            "endpoint_category",
            text("started_at DESC"),
        ),
        Index(
            "ix_external_api_requests_fixture",
            "fixture_id",
            text("started_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_category: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="SET NULL"), nullable=True
    )
    league_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minute_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[str] = mapped_column(String(2), nullable=False)
    degradation_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    estimated_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)


class QuotaBucket(Base):
    __tablename__ = "quota_buckets"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "window",
            "observed_at",
            name="uq_quota_buckets_provider_window_observed",
        ),
        Index(
            "ix_quota_buckets_provider_window_observed",
            "provider",
            "window",
            text("observed_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    window: Mapped[str] = mapped_column(String(16), nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_value: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OddsEventMapping(Base):
    """Deterministic mapping: provider event id ↔ internal fixture.

    Resolved strictly (teams + kickoff, ambiguity → error, never guess)
    and persisted for reuse so subsequent odds polls skip resolution.
    """

    __tablename__ = "odds_event_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_odds_event_mappings_provider_event",
        ),
        Index("ix_odds_event_mappings_fixture", "fixture_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    sport_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    home_team_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commence_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mapped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
