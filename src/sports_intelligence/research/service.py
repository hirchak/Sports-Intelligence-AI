from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.core.phases import ResearchState
from sports_intelligence.db.models import (
    ResearchClaim,
    ResearchDocument,
    ResearchRun,
)


@dataclass(frozen=True)
class ResearchClaimView:
    id: uuid.UUID
    document_id: uuid.UUID
    claim_type: str
    claim_text: str
    confidence: float
    team_id: uuid.UUID | None
    conflict_flag: bool
    conflicting_claim_id: uuid.UUID | None
    extraction_version: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ResearchDocumentView:
    id: uuid.UUID
    url: str
    domain: str
    title: str
    published_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    relevance_score: float | None
    snippet: str | None
    provider: str
    metadata: dict[str, Any]
    claims: list[ResearchClaimView] = field(default_factory=list)


@dataclass(frozen=True)
class FixtureResearchView:
    fixture_id: uuid.UUID
    status: str
    last_captured_at: datetime | None
    documents_count: int
    claims_count: int
    conflicts_count: int
    documents: list[ResearchDocumentView] = field(default_factory=list)
    claims: list[ResearchClaimView] = field(default_factory=list)


async def get_research_for_fixture(
    session: AsyncSession,
    fixture_id: uuid.UUID,
    *,
    as_of: datetime | None = None,
) -> FixtureResearchView:
    """Read research evidence for a fixture with strict provenance & anti-leakage control.

    Enforces:
    - `retrieved_at <= as_of`
    - `published_at <= as_of` (where publication date exists;
      unknown dates stay None, never invented)
    - documents or claims observed/published after `as_of` are excluded from historical replay.
    """
    as_of_aware = (
        as_of.astimezone(UTC)
        if as_of and as_of.tzinfo
        else (as_of.replace(tzinfo=UTC) if as_of else None)
    )

    # 1. Fetch latest research run at or before as_of
    run_stmt = select(ResearchRun).where(ResearchRun.fixture_id == fixture_id)
    if as_of_aware is not None:
        run_stmt = run_stmt.where(ResearchRun.captured_at <= as_of_aware)
    run_stmt = run_stmt.order_by(ResearchRun.captured_at.desc()).limit(1)
    run_row = (await session.execute(run_stmt)).scalar_one_or_none()

    if run_row is None:
        return FixtureResearchView(
            fixture_id=fixture_id,
            status=ResearchState.NO_USEFUL_RESULTS.value,
            last_captured_at=None,
            documents_count=0,
            claims_count=0,
            conflicts_count=0,
            documents=[],
            claims=[],
        )

    # 2. Fetch documents satisfying strict as_of anti-leakage constraints
    doc_conditions = [ResearchDocument.fixture_id == fixture_id]
    if as_of_aware is not None:
        doc_conditions.append(ResearchDocument.retrieved_at <= as_of_aware)
        doc_conditions.append(
            or_(
                ResearchDocument.published_at.is_(None),
                ResearchDocument.published_at <= as_of_aware,
            )
        )

    doc_stmt = (
        select(ResearchDocument)
        .where(*doc_conditions)
        .order_by(ResearchDocument.retrieved_at.desc())
    )
    doc_rows = (await session.execute(doc_stmt)).scalars().all()

    if not doc_rows:
        return FixtureResearchView(
            fixture_id=fixture_id,
            status=run_row.status,
            last_captured_at=run_row.captured_at,
            documents_count=0,
            claims_count=0,
            conflicts_count=0,
            documents=[],
            claims=[],
        )

    doc_ids = [d.id for d in doc_rows]

    # 3. Fetch claims linked to these documents
    claim_stmt = (
        select(ResearchClaim)
        .where(
            ResearchClaim.fixture_id == fixture_id,
            ResearchClaim.document_id.in_(doc_ids),
        )
        .order_by(ResearchClaim.created_at.desc())
    )
    claim_rows = (await session.execute(claim_stmt)).scalars().all()

    claims_by_doc: dict[uuid.UUID, list[ResearchClaimView]] = {}
    claim_views: list[ResearchClaimView] = []
    conflicts_count = 0

    for c in claim_rows:
        view = ResearchClaimView(
            id=c.id,
            document_id=c.document_id,
            claim_type=c.claim_type,
            claim_text=c.claim_text,
            confidence=c.confidence,
            team_id=c.team_id,
            conflict_flag=c.conflict_flag,
            conflicting_claim_id=c.conflicting_claim_id,
            extraction_version=c.extraction_version,
            metadata=c.metadata_jsonb,
            created_at=c.created_at,
        )
        claim_views.append(view)
        claims_by_doc.setdefault(c.document_id, []).append(view)
        if c.conflict_flag:
            conflicts_count += 1

    doc_views: list[ResearchDocumentView] = [
        ResearchDocumentView(
            id=d.id,
            url=d.url,
            domain=d.domain,
            title=d.title,
            published_at=d.published_at,
            retrieved_at=d.retrieved_at,
            content_hash=d.content_hash,
            relevance_score=d.relevance_score,
            snippet=d.snippet,
            provider=d.provider,
            metadata=d.metadata_jsonb,
            claims=claims_by_doc.get(d.id, []),
        )
        for d in doc_rows
    ]

    return FixtureResearchView(
        fixture_id=fixture_id,
        status=run_row.status,
        last_captured_at=run_row.captured_at,
        documents_count=len(doc_views),
        claims_count=len(claim_views),
        conflicts_count=conflicts_count,
        documents=doc_views,
        claims=claim_views,
    )
