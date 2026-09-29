"""M5: research runs, documents, and claims tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _UUID = postgresql.UUID(as_uuid=True)
    _JSONB = postgresql.JSONB(astext_type=sa.Text())

    # 1. research_runs
    op.create_table(
        "research_runs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("queries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claims_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_jsonb", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_runs_fixture_captured",
        "research_runs",
        ["fixture_id", sa.text("captured_at DESC")],
    )

    # 2. research_documents
    op.create_table(
        "research_documents",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("run_id", _UUID, nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("metadata_jsonb", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_documents_fixture_retrieved",
        "research_documents",
        ["fixture_id", sa.text("retrieved_at DESC")],
    )
    op.create_index(
        "ix_research_documents_fixture_published",
        "research_documents",
        ["fixture_id", sa.text("published_at DESC")],
    )
    op.create_index("ix_research_documents_content_hash", "research_documents", ["content_hash"])
    op.create_index("ix_research_documents_domain", "research_documents", ["domain"])

    # 3. research_claims
    op.create_table(
        "research_claims",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("document_id", _UUID, nullable=False),
        sa.Column("fixture_id", _UUID, nullable=False),
        sa.Column("team_id", _UUID, nullable=True),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("conflicting_claim_id", _UUID, nullable=True),
        sa.Column(
            "extraction_version", sa.String(length=32), nullable=False, server_default="v1_rule"
        ),
        sa.Column("metadata_jsonb", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_claims_fixture_created",
        "research_claims",
        ["fixture_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_research_claims_document", "research_claims", ["document_id"])
    op.create_index(
        "ix_research_claims_fixture_type", "research_claims", ["fixture_id", "claim_type"]
    )


def downgrade() -> None:
    op.drop_table("research_claims")
    op.drop_table("research_documents")
    op.drop_table("research_runs")
