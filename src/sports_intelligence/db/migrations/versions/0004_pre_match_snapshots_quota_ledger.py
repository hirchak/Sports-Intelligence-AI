"""M4 pre-match snapshots, odds, quota ledger

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True)


def _snapshots_group() -> None:
    op.create_table(
        "standings_snapshots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("league_id", _UUID, nullable=False),
        sa.Column("season_id", _UUID, nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("payload_id", _UUID, nullable=True),
        sa.Column("rows_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "league_id",
            "season_id",
            "captured_at",
            name="uq_standings_provider_league_season_captured",
        ),
    )
    op.create_index(
        op.f("ix_standings_snapshots_league_captured"),
        "standings_snapshots",
        ["league_id", sa.text("captured_at DESC")],
    )

    op.create_table(
        "team_statistics_snapshots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("team_id", _UUID, nullable=False),
        sa.Column("league_id", _UUID, nullable=False),
        sa.Column("season_id", _UUID, nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_id", _UUID, nullable=True),
        sa.Column("metrics_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "team_id",
            "league_id",
            "season_id",
            "captured_at",
            name="uq_team_stats_provider_team_league_season_captured",
        ),
    )
    op.create_index(
        op.f("ix_team_statistics_snapshots_team_captured"),
        "team_statistics_snapshots",
        ["team_id", sa.text("captured_at DESC")],
    )
    op.create_index(
        op.f("ix_team_statistics_snapshots_league_captured"),
        "team_statistics_snapshots",
        ["league_id", sa.text("captured_at DESC")],
    )

    op.create_table(
        "team_form_snapshots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("team_id", _UUID, nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size", sa.SmallInteger, nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("metrics_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("source_fingerprint", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "as_of",
            "window_size",
            "scope",
            name="uq_team_form_team_asof_window_scope",
        ),
    )

    op.create_table(
        "availability_snapshots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("team_id", _UUID, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_id", _UUID, nullable=True),
        sa.Column("players_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("impact_flags_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("conflicts_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("availability_state", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "fixture_id",
            "team_id",
            "captured_at",
            name="uq_availability_provider_fixture_team_captured",
        ),
    )
    op.create_index(
        op.f("ix_availability_snapshots_fixture_team_captured"),
        "availability_snapshots",
        ["fixture_id", "team_id", sa.text("captured_at DESC")],
    )

    op.create_table(
        "lineup_snapshots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("team_id", _UUID, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_id", _UUID, nullable=True),
        sa.Column("confirmed", sa.Boolean, nullable=False),
        sa.Column("formation", sa.String(length=16), nullable=True),
        sa.Column("players_jsonb", postgresql.JSONB, nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "fixture_id",
            "team_id",
            "captured_at",
            name="uq_lineups_provider_fixture_team_captured",
        ),
    )
    op.create_index(
        op.f("ix_lineup_snapshots_fixture_team_captured"),
        "lineup_snapshots",
        ["fixture_id", "team_id", sa.text("captured_at DESC")],
    )


def _odds_group() -> None:
    op.create_table(
        "odds_snapshot_sets",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_whitelist_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("payload_id", _UUID, nullable=True),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_odds_snapshot_sets_fixture_captured"),
        "odds_snapshot_sets",
        ["fixture_id", sa.text("captured_at DESC")],
    )

    op.create_table(
        "odds_prices",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("snapshot_set_id", _UUID, nullable=False),
        sa.Column("bookmaker", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("selection", sa.String(length=64), nullable=False),
        sa.Column("line", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("decimal_odds", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("implied_probability", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("no_vig_probability", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_set_id"], ["odds_snapshot_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("decimal_odds > 1.0", name="ck_odds_prices_decimal_gt_one"),
    )
    op.create_index(
        op.f("ix_odds_prices_snapshot_market"),
        "odds_prices",
        ["snapshot_set_id", "market"],
    )


def _quota_group() -> None:
    op.create_table(
        "external_api_requests",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint_category", sa.String(length=64), nullable=False),
        sa.Column("fixture_id", _UUID, nullable=True),
        sa.Column("league_id", _UUID, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("daily_remaining", sa.Integer(), nullable=True),
        sa.Column("minute_remaining", sa.Integer(), nullable=True),
        sa.Column("priority", sa.String(length=2), nullable=False),
        sa.Column("degradation_mode", sa.String(length=16), nullable=False),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_external_api_requests_provider_started"),
        "external_api_requests",
        ["provider", sa.text("started_at DESC")],
    )
    op.create_index(
        op.f("ix_external_api_requests_category_started"),
        "external_api_requests",
        ["endpoint_category", sa.text("started_at DESC")],
    )
    op.create_index(
        op.f("ix_external_api_requests_fixture"),
        "external_api_requests",
        ["fixture_id", sa.text("started_at DESC")],
    )

    op.create_table(
        "quota_buckets",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("window", sa.String(length=16), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("remaining_value", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "window",
            "observed_at",
            name="uq_quota_buckets_provider_window_observed",
        ),
    )
    op.create_index(
        op.f("ix_quota_buckets_provider_window_observed"),
        "quota_buckets",
        ["provider", "window", sa.text("observed_at DESC")],
    )


def upgrade() -> None:
    _snapshots_group()
    _odds_group()
    _quota_group()


def downgrade() -> None:
    op.drop_table("quota_buckets")
    op.drop_table("external_api_requests")
    op.drop_table("odds_prices")
    op.drop_table("odds_snapshot_sets")
    op.drop_table("lineup_snapshots")
    op.drop_table("availability_snapshots")
    op.drop_table("team_form_snapshots")
    op.drop_table("team_statistics_snapshots")
    op.drop_table("standings_snapshots")
