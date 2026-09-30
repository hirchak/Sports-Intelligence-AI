"""M6.1: immutable fixture metadata snapshots, form payload linkage,
quality policy and feature provenance.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. fixture_metadata_snapshots
    op.create_table(
        "fixture_metadata_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_fixture_id", sa.String(64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "league_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "season_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "home_team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "away_team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_home_team_name", sa.String(128), nullable=False),
        sa.Column("observed_away_team_name", sa.String(128), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue", sa.String(128), nullable=True),
        sa.Column("round", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "payload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_version", sa.String(32), nullable=False, server_default=sa.text("'v1'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_fixture_metadata_snapshots_fixture_captured",
        "fixture_metadata_snapshots",
        ["fixture_id", sa.text("captured_at DESC")],
    )
    op.create_index(
        "ix_fixture_metadata_snapshots_provider_external",
        "fixture_metadata_snapshots",
        ["provider", "provider_fixture_id"],
    )

    # 2. Add payload_id to team_form_snapshots
    op.add_column(
        "team_form_snapshots",
        sa.Column(
            "payload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_provider_payloads.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 3. Add source_fingerprint and quality_policy_jsonb to data_quality_reports
    op.add_column(
        "data_quality_reports",
        sa.Column("source_fingerprint", sa.String(255), nullable=True),
    )
    op.add_column(
        "data_quality_reports",
        sa.Column("quality_policy_jsonb", postgresql.JSONB, nullable=True),
    )
    op.create_unique_constraint(
        "uq_data_quality_reports_identity",
        "data_quality_reports",
        ["fixture_id", "forecast_phase", "as_of", "schema_version", "source_fingerprint"],
    )

    # 4. Add feature_provenance_jsonb to feature_snapshots
    op.add_column(
        "feature_snapshots",
        sa.Column("feature_provenance_jsonb", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    # 4. Drop feature_provenance_jsonb from feature_snapshots
    op.drop_column("feature_snapshots", "feature_provenance_jsonb")

    # 3. Drop unique constraint and columns from data_quality_reports
    op.drop_constraint("uq_data_quality_reports_identity", "data_quality_reports", type_="unique")
    op.drop_column("data_quality_reports", "quality_policy_jsonb")
    op.drop_column("data_quality_reports", "source_fingerprint")

    # 2. Drop payload_id from team_form_snapshots
    op.drop_column("team_form_snapshots", "payload_id")

    # 1. Drop fixture_metadata_snapshots
    op.drop_index(
        "ix_fixture_metadata_snapshots_provider_external",
        table_name="fixture_metadata_snapshots",
    )
    op.drop_index(
        "ix_fixture_metadata_snapshots_fixture_captured",
        table_name="fixture_metadata_snapshots",
    )
    op.drop_table("fixture_metadata_snapshots")
