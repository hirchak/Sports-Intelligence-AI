"""M4.1: lineup publication state, ledger cost columns, odds event mappings

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lineup publication semantics (NOT_YET_PUBLISHED / CONFIRMED /
    # UNSUPPORTED / PROVIDER_ERROR). Existing rows: confirmed → CONFIRMED.
    op.add_column(
        "lineup_snapshots",
        sa.Column(
            "publication_state",
            sa.String(length=24),
            nullable=False,
            server_default="NOT_YET_PUBLISHED",
        ),
    )
    op.execute("UPDATE lineup_snapshots SET publication_state = 'CONFIRMED' WHERE confirmed = true")

    # Quota ledger cost telemetry (The Odds API bills in credits).
    op.add_column(
        "external_api_requests",
        sa.Column("estimated_cost", sa.Integer(), nullable=True),
    )
    op.add_column(
        "external_api_requests",
        sa.Column("actual_cost", sa.Integer(), nullable=True),
    )

    _UUID = postgresql.UUID(as_uuid=True)
    op.create_table(
        "odds_event_mappings",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("sport_key", sa.String(length=64), nullable=False),
        sa.Column("provider_event_id", sa.String(length=64), nullable=False),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("home_team_name", sa.String(length=128), nullable=True),
        sa.Column("away_team_name", sa.String(length=128), nullable=True),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mapped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_odds_event_mappings_provider_event"
        ),
    )
    op.create_index(
        "ix_odds_event_mappings_fixture",
        "odds_event_mappings",
        ["fixture_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_odds_event_mappings_fixture", table_name="odds_event_mappings")
    op.drop_table("odds_event_mappings")
    op.drop_column("external_api_requests", "actual_cost")
    op.drop_column("external_api_requests", "estimated_cost")
    op.drop_column("lineup_snapshots", "publication_state")
