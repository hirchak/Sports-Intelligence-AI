"""create discovery tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("league_id", "name", name="uq_seasons_league_name"),
    )

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "fixtures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("home_team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("away_team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue", sa.String(length=128), nullable=True),
        sa.Column("round", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "league_id",
            "home_team_id",
            "away_team_id",
            "kickoff_at",
            name="uq_fixtures_natural_key",
        ),
    )
    op.create_index(op.f("ix_fixtures_kickoff_at"), "fixtures", ["kickoff_at"], unique=False)
    op.create_index(op.f("ix_fixtures_league_id"), "fixtures", ["league_id"], unique=False)
    op.create_index(op.f("ix_fixtures_status"), "fixtures", ["status"], unique=False)

    op.create_table(
        "provider_entity_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("internal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "entity_type", "external_id", name="uq_provider_entity_ids_identity"
        ),
    )
    op.create_index(
        op.f("ix_provider_entity_ids_internal_entity_id"),
        "provider_entity_ids",
        ["internal_entity_id"],
        unique=False,
    )

    op.create_table(
        "raw_provider_payloads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint_family", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "endpoint_family", "payload_hash", name="uq_raw_payloads_hash"
        ),
    )
    op.create_index(
        op.f("ix_raw_provider_payloads_payload_hash"),
        "raw_provider_payloads",
        ["payload_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_raw_provider_payloads_retrieved_at"),
        "raw_provider_payloads",
        ["retrieved_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_raw_provider_payloads_retrieved_at"), table_name="raw_provider_payloads")
    op.drop_index(op.f("ix_raw_provider_payloads_payload_hash"), table_name="raw_provider_payloads")
    op.drop_table("raw_provider_payloads")
    op.drop_index(
        op.f("ix_provider_entity_ids_internal_entity_id"), table_name="provider_entity_ids"
    )
    op.drop_table("provider_entity_ids")
    op.drop_index(op.f("ix_fixtures_status"), table_name="fixtures")
    op.drop_index(op.f("ix_fixtures_league_id"), table_name="fixtures")
    op.drop_index(op.f("ix_fixtures_kickoff_at"), table_name="fixtures")
    op.drop_table("fixtures")
    op.drop_table("teams")
    op.drop_table("seasons")
    op.drop_table("leagues")
