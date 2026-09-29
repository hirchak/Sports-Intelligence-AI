from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from sports_intelligence.core.phases import ResearchState
from sports_intelligence.db.models import (
    ResearchClaim,
    ResearchDocument,
    ResearchRun,
)
from sports_intelligence.research.service import get_research_for_fixture


@pytest.mark.asyncio
async def test_get_research_for_fixture_anti_leakage_as_of() -> None:
    fixture_id = uuid.uuid4()
    t0 = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=2)

    run = ResearchRun(
        id=uuid.uuid4(),
        fixture_id=fixture_id,
        phase="morning",
        status=ResearchState.AVAILABLE.value,
        provider="mock",
        queries_count=2,
        documents_count=2,
        claims_count=2,
        conflicts_count=0,
        captured_at=t1,
    )

    doc_past = ResearchDocument(
        id=uuid.uuid4(),
        fixture_id=fixture_id,
        run_id=run.id,
        url="https://site.com/past",
        domain="site.com",
        title="Past News",
        published_at=t0,
        retrieved_at=t0,
        content_hash="hash_past",
        relevance_score=0.9,
        snippet="Past snippet",
        provider="mock",
        metadata_jsonb={},
    )

    claim_past = ResearchClaim(
        id=uuid.uuid4(),
        document_id=doc_past.id,
        fixture_id=fixture_id,
        claim_type="injury",
        claim_text="Past injury news",
        confidence=0.8,
        conflict_flag=False,
        conflicting_claim_id=None,
        extraction_version="v1_rule",
        metadata_jsonb={},
        extracted_at=t0,
        created_at=t0,
    )

    # Session mock simulating SQLAlchemy results
    session = AsyncMock()

    # Step 1: run_stmt returns run
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run

    # Step 2: doc_stmt returns doc_past (when filtered with as_of <= t1)
    doc_result = MagicMock()
    doc_result.scalars.return_value.all.return_value = [doc_past]

    # Step 3: claim_stmt returns claim_past
    claim_result = MagicMock()
    claim_result.scalars.return_value.all.return_value = [claim_past]

    session.execute.side_effect = [run_result, doc_result, claim_result]

    view = await get_research_for_fixture(session, fixture_id, as_of=t1)

    assert view.fixture_id == fixture_id
    assert view.status == ResearchState.AVAILABLE.value
    assert len(view.documents) == 1
    assert view.documents[0].url == "https://site.com/past"
    assert len(view.claims) == 1
    assert view.claims[0].claim_text == "Past injury news"


@pytest.mark.asyncio
async def test_claim_level_as_of_safety_filtering() -> None:
    """Regression for M5.1 §2:

    Document retrieved at T0
    Claim extracted at T2
    Query as_of T1 (T0 < T1 < T2):
      → document may be visible
      → claim MUST NOT be visible
    Query as_of T3 (T3 > T2):
      → claim visible
    """
    fixture_id = uuid.uuid4()
    t0 = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)

    run = ResearchRun(
        id=uuid.uuid4(),
        fixture_id=fixture_id,
        phase="morning",
        status=ResearchState.AVAILABLE.value,
        provider="mock",
        queries_count=1,
        documents_count=1,
        claims_count=1,
        conflicts_count=0,
        captured_at=t0,
    )

    doc = ResearchDocument(
        id=uuid.uuid4(),
        fixture_id=fixture_id,
        run_id=run.id,
        url="https://site.com/doc",
        domain="site.com",
        title="Squad Update",
        published_at=t0,
        retrieved_at=t0,  # retrieved at T0
        content_hash="hash_doc",
        relevance_score=0.9,
        snippet="Snippet",
        provider="mock",
        metadata_jsonb={},
    )

    # Claim extracted at T2 (after T1)
    claim = ResearchClaim(
        id=uuid.uuid4(),
        document_id=doc.id,
        fixture_id=fixture_id,
        claim_type="availability",
        claim_text="Late injury extracted at T2",
        confidence=0.85,
        extracted_at=t2,
        created_at=t2,
        conflict_flag=False,
        conflicting_claim_id=None,
        extraction_version="v1_rule",
        metadata_jsonb={},
    )

    # Case 1: as_of = T1 (doc visible, claim excluded because extracted_at=T2 > T1)
    session_t1 = AsyncMock()
    run_res1 = MagicMock()
    run_res1.scalar_one_or_none.return_value = run
    doc_res1 = MagicMock()
    doc_res1.scalars.return_value.all.return_value = [doc]
    claim_res1 = MagicMock()
    # When query filters extracted_at <= T1, claim is NOT returned:
    claim_res1.scalars.return_value.all.return_value = []
    session_t1.execute.side_effect = [run_res1, doc_res1, claim_res1]

    view_t1 = await get_research_for_fixture(session_t1, fixture_id, as_of=t1)
    assert len(view_t1.documents) == 1
    assert len(view_t1.claims) == 0  # Claim MUST NOT be visible at T1!

    # Case 2: as_of = T3 (both doc and claim visible because T3 > T2)
    session_t3 = AsyncMock()
    run_res3 = MagicMock()
    run_res3.scalar_one_or_none.return_value = run
    doc_res3 = MagicMock()
    doc_res3.scalars.return_value.all.return_value = [doc]
    claim_res3 = MagicMock()
    # When query filters extracted_at <= T3, claim IS returned:
    claim_res3.scalars.return_value.all.return_value = [claim]
    session_t3.execute.side_effect = [run_res3, doc_res3, claim_res3]

    view_t3 = await get_research_for_fixture(session_t3, fixture_id, as_of=t3)
    assert len(view_t3.documents) == 1
    assert len(view_t3.claims) == 1
    assert view_t3.claims[0].claim_text == "Late injury extracted at T2"


@pytest.mark.asyncio
async def test_get_research_for_fixture_no_runs_returns_empty() -> None:
    fixture_id = uuid.uuid4()
    session = AsyncMock()

    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = None
    session.execute.return_value = run_result

    view = await get_research_for_fixture(session, fixture_id)
    assert view.fixture_id == fixture_id
    assert view.status == ResearchState.NO_USEFUL_RESULTS.value
    assert len(view.documents) == 0
    assert len(view.claims) == 0
