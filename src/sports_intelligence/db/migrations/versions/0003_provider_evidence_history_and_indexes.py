"""provider evidence history, atomic identity and composite indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint_family", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["payload_id"], ["raw_provider_payloads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_provider_observations_payload_id"),
        "provider_observations",
        ["payload_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_observations_retrieved_at"),
        "provider_observations",
        ["retrieved_at"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO provider_observations
            (id, payload_id, provider, endpoint_family, request_fingerprint,
             retrieved_at, response_status)
        SELECT
            gen_random_uuid(), id, provider, endpoint_family, request_fingerprint,
            retrieved_at, response_status
        FROM raw_provider_payloads
        """
    )

    op.add_column(
        "raw_provider_payloads",
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.drop_index(op.f("ix_raw_provider_payloads_retrieved_at"), table_name="raw_provider_payloads")
    op.drop_column("raw_provider_payloads", "request_fingerprint")
    op.drop_column("raw_provider_payloads", "retrieved_at")
    op.drop_column("raw_provider_payloads", "response_status")

    op.alter_column("teams", "name", existing_type=sa.String(length=128), nullable=True)

    op.drop_index(op.f("ix_fixtures_league_id"), table_name="fixtures")
    op.drop_index(op.f("ix_fixtures_status"), table_name="fixtures")
    op.create_index(
        op.f("ix_fixtures_league_kickoff"),
        "fixtures",
        ["league_id", "kickoff_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fixtures_status_kickoff"),
        "fixtures",
        ["status", "kickoff_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fixtures_status_kickoff"), table_name="fixtures")
    op.drop_index(op.f("ix_fixtures_league_kickoff"), table_name="fixtures")
    op.create_index(op.f("ix_fixtures_status"), "fixtures", ["status"], unique=False)
    op.create_index(op.f("ix_fixtures_league_id"), "fixtures", ["league_id"], unique=False)

    op.alter_column("teams", "name", existing_type=sa.String(length=128), nullable=False)

    op.add_column(
        "raw_provider_payloads",
        sa.Column("response_status", sa.Integer(), nullable=True),
    )
    op.add_column(
        "raw_provider_payloads",
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "raw_provider_payloads",
        sa.Column("request_fingerprint", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE raw_provider_payloads AS payload
        SET request_fingerprint = obs.request_fingerprint,
            retrieved_at = obs.retrieved_at,
            response_status = obs.response_status
        FROM (
            SELECT DISTINCT ON (payload_id)
                payload_id, request_fingerprint, retrieved_at, response_status
            FROM provider_observations
            ORDER BY payload_id, retrieved_at DESC
        ) AS obs
        WHERE payload.id = obs.payload_id
        """
    )
    op.alter_column(
        "raw_provider_payloads",
        "request_fingerprint",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "raw_provider_payloads",
        "retrieved_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index(
        op.f("ix_raw_provider_payloads_retrieved_at"),
        "raw_provider_payloads",
        ["retrieved_at"],
        unique=False,
    )
    op.drop_column("raw_provider_payloads", "first_seen_at")

    op.drop_index(op.f("ix_provider_observations_retrieved_at"), table_name="provider_observations")
    op.drop_index(op.f("ix_provider_observations_payload_id"), table_name="provider_observations")
    op.drop_table("provider_observations")
