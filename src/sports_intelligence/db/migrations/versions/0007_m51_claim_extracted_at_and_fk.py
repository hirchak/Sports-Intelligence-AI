"""M5.1: research claims extracted_at timestamp and deferrable self-referential FK

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add extracted_at column to research_claims
    op.add_column(
        "research_claims",
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 2. Add descending composite index on (fixture_id, extracted_at DESC)
    op.create_index(
        "ix_research_claims_fixture_extracted",
        "research_claims",
        ["fixture_id", sa.text("extracted_at DESC")],
    )

    # 3. Add deferrable self-referential foreign key for conflicting_claim_id
    op.create_foreign_key(
        "fk_research_claims_conflicting_claim_id",
        "research_claims",
        "research_claims",
        ["conflicting_claim_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_claims_conflicting_claim_id", "research_claims", type_="foreignkey"
    )
    op.drop_index("ix_research_claims_fixture_extracted", table_name="research_claims")
    op.drop_column("research_claims", "extracted_at")
