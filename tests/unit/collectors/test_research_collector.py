from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    Priority,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.research_collector import ResearchCollector
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory, ResearchState
from sports_intelligence.db.models import Fixture, Team
from sports_intelligence.providers.search.mock import MockSearchProvider


def _make_context(
    *,
    settings: Settings,
    session: Any,
    provider: Any = None,
) -> CollectorContext:
    lock_mgr = MagicMock()
    lock_mgr.acquire = AsyncMock(return_value=True)
    lock_mgr.release = AsyncMock()

    quota_mgr = MagicMock()
    quota_mgr.check_budget = AsyncMock(return_value=True)
    quota_mgr.record_request = AsyncMock()
    quota_mgr.observe = AsyncMock(return_value=(100, 10, MagicMock(value="NORMAL")))

    policy = FreshnessPolicy(settings)
    session.add = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock()

    return CollectorContext(
        settings=settings,
        session_factory=session_factory,
        redis=MagicMock(),
        locks=lock_mgr,
        quota=quota_mgr,
        freshness=policy,
        provider=provider,
    )


def test_research_collector_metadata() -> None:
    collector = ResearchCollector()
    assert collector.name == "research"
    assert collector.category == FreshnessCategory.RESEARCH
    assert collector.priority == Priority.P3


@pytest.mark.asyncio
async def test_research_collector_fetch_with_mock_provider() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
    )
    fid = uuid.uuid4()
    hid = uuid.uuid4()
    aid = uuid.uuid4()
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)

    fixture = Fixture(id=fid, home_team_id=hid, away_team_id=aid, kickoff_at=kickoff)
    home_team = Team(id=hid, name="Arsenal")
    away_team = Team(id=aid, name="Chelsea")

    session = AsyncMock()
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock

    provider = MockSearchProvider()
    ctx = _make_context(settings=settings, session=session, provider=provider)
    collector = ResearchCollector()

    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["fixture_id"] == str(fid)
    assert result.normalized["provider"] == "mock"
    assert result.normalized["queries_count"] > 0
    assert result.normalized["documents_count"] > 0
    assert result.normalized["status"] == ResearchState.AVAILABLE.value
    assert len(provider.history) > 0


@pytest.mark.asyncio
async def test_research_collector_disabled_provider_returns_no_useful_results() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="",
        research_enabled=False,
    )
    fid = uuid.uuid4()
    hid = uuid.uuid4()
    aid = uuid.uuid4()
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)

    fixture = Fixture(id=fid, home_team_id=hid, away_team_id=aid, kickoff_at=kickoff)
    home_team = Team(id=hid, name="Arsenal")
    away_team = Team(id=aid, name="Chelsea")

    session = AsyncMock()
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock

    # No provider passed
    ctx = _make_context(settings=settings, session=session, provider=None)
    collector = ResearchCollector()

    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["status"] == ResearchState.NO_USEFUL_RESULTS.value
    assert result.normalized["documents_count"] == 0
    assert result.normalized["claims_count"] == 0


@pytest.mark.asyncio
async def test_research_collector_persist_returns_snapshot_ref() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
    )
    session = AsyncMock()
    ctx = _make_context(settings=settings, session=session)
    collector = ResearchCollector()

    fid = uuid.uuid4()
    payload = {
        "fixture_id": str(fid),
        "phase": ForecastPhase.MORNING.value,
        "status": ResearchState.AVAILABLE.value,
        "provider": "mock",
        "queries_count": 2,
        "documents_count": 1,
        "claims_count": 1,
        "conflicts_count": 0,
        "captured_at": datetime.now(UTC).isoformat(),
        "documents": [
            {
                "url": "https://news.com/1",
                "domain": "news.com",
                "title": "Arsenal news",
                "snippet": "Saka is fit",
                "published_at": None,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "content_hash": "abc123456",
                "relevance_score": 0.85,
                "provider": "mock",
                "metadata": {},
                "claims": [
                    {
                        "claim_type": "injury",
                        "claim_text": "Saka is fit",
                        "confidence": 0.8,
                        "team_id": None,
                        "conflict_flag": False,
                        "conflicting_claim_id": None,
                        "extraction_version": "v1_rule",
                        "metadata": {},
                    }
                ],
            }
        ],
    }

    res = CollectorResult(raw_payload={"status": "ok"}, normalized=payload)
    refs = await collector.persist(
        ctx,
        res,
        captured_at=datetime.now(UTC),
        source_fingerprint="fp123",
        payload_id=uuid.uuid4(),
        fixture_id=fid,
        phase=ForecastPhase.MORNING.value,
    )
    assert len(refs) == 1
    assert refs[0].table == "research_runs"
    assert refs[0].snapshot_id is not None
