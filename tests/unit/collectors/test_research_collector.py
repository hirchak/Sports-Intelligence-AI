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
    allowed_decision = MagicMock(denied=False, allowed=True, reason="ok")
    quota_mgr.reserve = AsyncMock(return_value=allowed_decision)
    quota_mgr.record_success = AsyncMock()
    quota_mgr.record_failure = AsyncMock()
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
    assert collector.owns_quota is True


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
    # Per-request quota ledger called for each query
    assert ctx.quota.reserve.call_count == result.normalized["queries_count"]
    assert ctx.quota.record_success.call_count == result.normalized["queries_count"]


@pytest.mark.asyncio
async def test_research_collector_disabled_provider_returns_disabled_state() -> None:
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

    assert result.normalized["status"] == ResearchState.DISABLED.value
    assert result.normalized["documents_count"] == 0
    assert result.normalized["claims_count"] == 0


@pytest.mark.asyncio
async def test_research_collector_quota_stops_when_denied() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_max_queries_per_fixture=6,
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

    # Allow 2 queries, then deny 3rd
    allowed = MagicMock(denied=False, allowed=True, reason="ok")
    denied = MagicMock(denied=True, allowed=False, reason="budget exceeded")
    ctx.quota.reserve.side_effect = [allowed, allowed, denied]

    collector = ResearchCollector()
    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    # Exactly 2 queries executed
    assert len(provider.history) == 2
    assert result.normalized["queries_count"] == 2
    assert ctx.quota.record_success.call_count == 2


@pytest.mark.asyncio
async def test_research_collector_provider_error_state() -> None:
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

    provider = MockSearchProvider(error_to_raise=RuntimeError("Search API down"))
    ctx = _make_context(settings=settings, session=session, provider=provider)
    collector = ResearchCollector()

    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["status"] == ResearchState.PROVIDER_ERROR.value
    assert result.normalized["documents_count"] == 0
    assert result.normalized["claims_count"] == 0
    assert ctx.quota.record_failure.call_count == 1


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


@pytest.mark.asyncio
async def test_extraction_unavailable_via_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_claim_extraction_enabled=False,
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

    assert result.normalized["status"] == ResearchState.EXTRACTION_UNAVAILABLE.value
    assert result.normalized["documents_count"] > 0
    assert result.normalized["claims_count"] == 0


@pytest.mark.asyncio
async def test_partial_failure_status_is_provider_error() -> None:
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

    from sports_intelligence.providers.errors import ProviderServerError
    from sports_intelligence.providers.search.base import SearchProvider, SearchResponse

    class MockSearchPartial(SearchProvider):
        name = "mock"

        def __init__(self):
            self.calls = 0

        async def search(self, query: str, **kwargs) -> SearchResponse:
            self.calls += 1
            if self.calls == 1:
                return SearchResponse(
                    query=query,
                    results=[
                        MagicMock(
                            url="http://mock",
                            domain="mock",
                            title="mock",
                            published_at=None,
                            retrieved_at=datetime.now(UTC),
                            content="mock",
                            score=1.0,
                            provider_metadata={},
                        )
                    ],
                    retrieved_at=datetime.now(UTC),
                    cost_estimate=1,
                    raw_payload={},
                )
            raise ProviderServerError("Failed on second call")

    provider = MockSearchPartial()
    ctx = _make_context(settings=settings, session=session, provider=provider)
    collector = ResearchCollector()

    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["status"] == ResearchState.PROVIDER_ERROR.value
    assert "details" in result.normalized
    assert result.normalized["details"]["partial_failure"] is True
    assert result.normalized["documents_count"] == 1


@pytest.mark.asyncio
async def test_provider_error_run_not_fresh() -> None:
    collector = ResearchCollector()
    session = AsyncMock()
    row_mock = MagicMock()
    # (captured_at, run_id, status)
    row_mock.first.return_value = (
        datetime.now(UTC),
        uuid.uuid4(),
        ResearchState.PROVIDER_ERROR.value,
    )
    session.execute.return_value = row_mock

    captured_at, run_id = await collector.latest_snapshot(session, fixture_id=uuid.uuid4())
    assert captured_at is None
    assert run_id is None
