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

    # 1b. Backfill legacy_baseline snapshot for pre-existing fixtures
    op.execute(
        """
        INSERT INTO fixture_metadata_snapshots (
            id,
            fixture_id,
            provider,
            provider_fixture_id,
            captured_at,
            league_id,
            season_id,
            home_team_id,
            away_team_id,
            observed_home_team_name,
            observed_away_team_name,
            kickoff_at,
            venue,
            round,
            status,
            payload_id,
            source_version,
            created_at
        )
        SELECT
            gen_random_uuid(),
            f.id,
            'legacy_baseline',
            NULL,
            clock_timestamp(),
            f.league_id,
            f.season_id,
            f.home_team_id,
            f.away_team_id,
            COALESCE(ht.name, 'Unknown'),
            COALESCE(at.name, 'Unknown'),
            f.kickoff_at,
            f.venue,
            f.round,
            f.status,
            NULL,
            'legacy_baseline',
            clock_timestamp()
        FROM fixtures f
        LEFT JOIN teams ht ON ht.id = f.home_team_id
        LEFT JOIN teams at ON at.id = f.away_team_id
        """
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

    # 3. Add source_fingerprint, quality_policy_jsonb, and policy_fingerprint
    # to data_quality_reports
    op.add_column(
        "data_quality_reports",
        sa.Column("source_fingerprint", sa.String(255), nullable=True),
    )
    op.add_column(
        "data_quality_reports",
        sa.Column("quality_policy_jsonb", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "data_quality_reports",
        sa.Column("policy_fingerprint", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_data_quality_reports_identity",
        "data_quality_reports",
        [
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "source_fingerprint",
            "policy_fingerprint",
        ],
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
    op.drop_column("data_quality_reports", "policy_fingerprint")
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
