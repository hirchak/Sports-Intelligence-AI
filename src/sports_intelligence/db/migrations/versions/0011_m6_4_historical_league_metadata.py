"""M6.4 historical league metadata authority

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixture_metadata_snapshots",
        sa.Column("observed_league_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fixture_metadata_snapshots",
        sa.Column("observed_league_slug", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE fixture_metadata_snapshots fms
        SET observed_league_name = COALESCE(l.name, 'Unknown'),
            observed_league_slug = COALESCE(l.slug, 'unknown')
        FROM leagues l
        WHERE fms.league_id = l.id
          AND fms.observed_league_name IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_column("fixture_metadata_snapshots", "observed_league_slug")
    op.drop_column("fixture_metadata_snapshots", "observed_league_name")
