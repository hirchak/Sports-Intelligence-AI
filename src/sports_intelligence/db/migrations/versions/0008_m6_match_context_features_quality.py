"""M6: feature snapshots, data quality reports, and immutable match contexts

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. feature_snapshots
    op.create_table(
        "feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("forecast_phase", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False, server_default="features_v1"),
        sa.Column("features_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("source_fingerprint", sa.String(255), nullable=False),
        sa.Column(
            "source_manifest_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "source_fingerprint",
            name="uq_feature_snapshots_identity",
        ),
    )
    op.create_index(
        "ix_feature_snapshots_fixture_as_of",
        "feature_snapshots",
        ["fixture_id", sa.text("as_of DESC")],
    )
    op.create_index(
        "ix_feature_snapshots_fixture_phase",
        "feature_snapshots",
        ["fixture_id", "forecast_phase"],
    )

    # 2. data_quality_reports
    op.create_table(
        "data_quality_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("forecast_phase", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False, server_default="quality_v1"),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("quality_band", sa.String(32), nullable=False),
        sa.Column("can_predict", sa.Boolean(), nullable=False),
        sa.Column("dimensions_jsonb", postgresql.JSONB, nullable=False),
        sa.Column(
            "critical_missing_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "missing_fields_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "warnings_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "conflicts_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "provider_errors_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "stale_sources_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "source_manifest_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_data_quality_reports_fixture_as_of",
        "data_quality_reports",
        ["fixture_id", sa.text("as_of DESC")],
    )
    op.create_index(
        "ix_data_quality_reports_fixture_phase",
        "data_quality_reports",
        ["fixture_id", "forecast_phase"],
    )

    # 3. match_contexts
    op.create_table(
        "match_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("forecast_phase", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "schema_version", sa.String(32), nullable=False, server_default="match_context_v1"
        ),
        sa.Column("context_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column(
            "data_quality_report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_quality_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "feature_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "context_hash",
            name="uq_match_contexts_identity",
        ),
    )
    op.create_index(
        "ix_match_contexts_fixture_as_of",
        "match_contexts",
        ["fixture_id", sa.text("as_of DESC")],
    )
    op.create_index(
        "ix_match_contexts_fixture_phase",
        "match_contexts",
        ["fixture_id", "forecast_phase"],
    )
    op.create_index(
        "ix_match_contexts_hash",
        "match_contexts",
        ["context_hash"],
    )


def downgrade() -> None:
    op.drop_table("match_contexts")
    op.drop_table("data_quality_reports")
    op.drop_table("feature_snapshots")
