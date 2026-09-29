from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from sports_intelligence.providers.search.base import SearchResultItem
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
async def test_provider_error_snapshot_and_run_info() -> None:
    collector = ResearchCollector()
    session = AsyncMock()
    now_dt = datetime.now(UTC)
    run_id = uuid.uuid4()
    row_mock = MagicMock()
    # (captured_at, run_id, status)
    row_mock.first.return_value = (now_dt, run_id, ResearchState.PROVIDER_ERROR.value)
    session.execute.return_value = row_mock

    # latest_snapshot returns real (captured_at, run_id)
    captured_at, snap_run_id = await collector.latest_snapshot(session, fixture_id=uuid.uuid4())
    assert captured_at == now_dt
    assert snap_run_id == run_id

    # latest_run_info returns status and retry_due_at
    info = await collector.latest_run_info(
        session, fixture_id=uuid.uuid4(), error_retry_ttl_seconds=900
    )
    assert info.captured_at == now_dt
    assert info.run_id == run_id
    assert info.status == ResearchState.PROVIDER_ERROR.value
    assert info.retry_due_at == now_dt + timedelta(seconds=900)


@pytest.mark.asyncio
async def test_collector_refresh_due_provider_error() -> None:
    from datetime import timedelta

    collector = ResearchCollector()
    now_dt = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)
    captured_at = datetime(2026, 9, 29, 11, 50, 0, tzinfo=UTC)  # 10m ago

    ctx = MagicMock()
    ctx.settings.research_provider_error_retry_seconds = 900  # 15m
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=lambda: "PROVIDER_ERROR")
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock()
    ctx.session_factory = session_factory

    # At 10m elapsed (< 15m error TTL): NOT due yet
    is_due = await collector.refresh_due(
        ctx, {"fixture_id": str(uuid.uuid4())}, captured_at=captured_at, now=now_dt
    )
    assert is_due is False

    # At 16m elapsed (>= 15m error TTL): IS due
    now_later = captured_at + timedelta(seconds=960)
    is_due_later = await collector.refresh_due(
        ctx, {"fixture_id": str(uuid.uuid4())}, captured_at=captured_at, now=now_later
    )
    assert is_due_later is True


def test_refresh_opportunity_suffix_error_and_quota() -> None:
    from datetime import timedelta

    from sports_intelligence.collectors.refresh import refresh_opportunity_suffix

    t0 = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)

    # 1. PROVIDER_ERROR uses error_due:<epoch>
    opp_err = refresh_opportunity_suffix(
        collector_name="research",
        kickoff_at=t0 + timedelta(hours=2),
        now=t0 + timedelta(minutes=16),
        windows_minutes=[120, 60, 20],
        ttl_seconds=6 * 3600,
        latest_captured_at=t0,
        status="PROVIDER_ERROR",
        error_retry_ttl_seconds=900,
    )
    expected_err_due = int((t0 + timedelta(seconds=900)).timestamp())
    assert opp_err == f"error_due:{expected_err_due}"

    # 2. QUOTA_DENIED uses quota_due:<epoch>
    opp_quota = refresh_opportunity_suffix(
        collector_name="research",
        kickoff_at=t0 + timedelta(hours=2),
        now=t0 + timedelta(minutes=16),
        windows_minutes=[120, 60, 20],
        ttl_seconds=6 * 3600,
        latest_captured_at=t0,
        status="QUOTA_DENIED",
        error_retry_ttl_seconds=900,
    )
    expected_quota_due = int((t0 + timedelta(seconds=900)).timestamp())
    assert opp_quota == f"quota_due:{expected_quota_due}"

    # 3. AVAILABLE uses normal due:<epoch>
    opp_avail = refresh_opportunity_suffix(
        collector_name="research",
        kickoff_at=t0 + timedelta(hours=2),
        now=t0 + timedelta(minutes=16),
        windows_minutes=[120, 60, 20],
        ttl_seconds=6 * 3600,
        latest_captured_at=t0,
        status="AVAILABLE",
    )
    expected_normal_due = int((t0 + timedelta(seconds=6 * 3600)).timestamp())
    assert opp_avail == f"due:{expected_normal_due}"


@pytest.mark.asyncio
async def test_quota_denied_before_first_request_zero_provider_calls() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
    )
    fid = uuid.uuid4()
    session = AsyncMock()
    fixture = Fixture(
        id=fid,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=datetime.now(UTC),
    )
    home_team = Team(id=fixture.home_team_id, name="Arsenal")
    away_team = Team(id=fixture.away_team_id, name="Chelsea")
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock

    provider = MockSearchProvider()
    provider.search = AsyncMock()

    ctx = _make_context(settings=settings, session=session, provider=provider)
    # Quota denied immediately
    ctx.quota.reserve = AsyncMock(
        return_value=MagicMock(denied=True, allowed=False, reason="daily_limit_exhausted")
    )

    collector = ResearchCollector()
    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    # ZERO provider calls
    assert provider.search.call_count == 0
    # ZERO failure / success telemetry records
    assert ctx.quota.record_failure.call_count == 0
    assert ctx.quota.record_success.call_count == 0

    assert result.normalized["status"] == ResearchState.QUOTA_DENIED.value
    assert result.normalized["details"]["reason"] == "daily_limit_exhausted"
    assert result.normalized["details"]["queries_planned"] > 0
    assert result.normalized["details"]["queries_succeeded"] == 0
    assert result.normalized["details"]["quota_denied"] is True


@pytest.mark.asyncio
async def test_quota_denied_after_first_query_retains_documents() -> None:
    from sports_intelligence.providers.search.base import SearchProvider, SearchResponse

    class MockSearchOneSuccess(SearchProvider):
        name = "mock"

        def __init__(self):
            self.calls = 0

        async def search(self, query: str, **kwargs) -> SearchResponse:
            self.calls += 1
            return SearchResponse(
                query=query,
                results=[
                    SearchResultItem(
                        url="http://mock-url.com",
                        domain="mock-url.com",
                        title="Mock Arsenal News",
                        published_at=None,
                        retrieved_at=datetime.now(UTC),
                        content="Arsenal midfielder is injured.",
                        score=0.9,
                        provider_metadata={},
                    )
                ],
                retrieved_at=datetime.now(UTC),
                cost_estimate=1,
                raw_payload={"query": query},
            )

    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_max_queries_per_fixture=2,
    )
    fid = uuid.uuid4()
    session = AsyncMock()
    fixture = Fixture(
        id=fid,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=datetime.now(UTC),
    )
    home_team = Team(id=fixture.home_team_id, name="Arsenal")
    away_team = Team(id=fixture.away_team_id, name="Chelsea")
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock

    provider = MockSearchOneSuccess()
    ctx = _make_context(settings=settings, session=session, provider=provider)

    reserve_calls = 0

    async def mock_reserve(**kwargs):
        nonlocal reserve_calls
        reserve_calls += 1
        if reserve_calls == 1:
            return MagicMock(denied=False, allowed=True, reason="ok")
        return MagicMock(denied=True, allowed=False, reason="minute_rate_limit")

    ctx.quota.reserve = AsyncMock(side_effect=mock_reserve)

    collector = ResearchCollector()
    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["status"] == ResearchState.QUOTA_DENIED.value
    # Documents and claims are preserved!
    assert result.normalized["documents_count"] == 1
    assert result.normalized["claims_count"] > 0
    assert result.normalized["details"]["reason"] == "minute_rate_limit"
    assert result.normalized["details"]["queries_succeeded"] == 1
    assert result.normalized["details"]["partial_failure"] is True
    assert result.normalized["details"]["quota_denied"] is True


def test_compute_retry_delay_429() -> None:
    from sports_intelligence.collectors.research_collector import compute_retry_delay
    from sports_intelligence.providers.errors import ProviderRateLimitError, ProviderServerError

    # 1. 429 with valid small Retry-After
    exc1 = ProviderRateLimitError("Rate limited", quota_headers={"retry-after": "2"})
    assert compute_retry_delay(exc1, 0, max_retry_after_seconds=30.0) == 2.0

    # 2. 429 with huge Retry-After capped at max
    exc2 = ProviderRateLimitError("Rate limited", quota_headers={"retry-after": "99999"})
    assert compute_retry_delay(exc2, 0, max_retry_after_seconds=30.0) == 30.0

    # 3. 429 with invalid Retry-After falls back to exponential
    exc3 = ProviderRateLimitError("Rate limited", quota_headers={"retry-after": "invalid"})
    assert compute_retry_delay(exc3, 0, max_retry_after_seconds=30.0) == 0.1
    assert compute_retry_delay(exc3, 1, max_retry_after_seconds=30.0) == 0.2

    # 4. 429 with negative Retry-After falls back to exponential
    exc4 = ProviderRateLimitError("Rate limited", quota_headers={"retry-after": "-5"})
    assert compute_retry_delay(exc4, 0, max_retry_after_seconds=30.0) == 0.1

    # 5. Non-429 error uses exponential fallback
    exc5 = ProviderServerError("500 internal error")
    assert compute_retry_delay(exc5, 0, max_retry_after_seconds=30.0) == 0.1
    assert compute_retry_delay(exc5, 2, max_retry_after_seconds=30.0) == 0.4


@pytest.mark.asyncio
async def test_failure_observation_timestamp_reflects_actual_failure_time() -> None:
    from datetime import timedelta

    from sports_intelligence.providers.errors import ProviderServerError
    from sports_intelligence.providers.search.base import SearchProvider

    t0 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=UTC)
    t2 = t0 + timedelta(seconds=2)
    clock_time = t0

    def clock():
        return clock_time

    class MockFailingProvider(SearchProvider):
        name = "mock"

        async def search(self, query: str, **kwargs):
            nonlocal clock_time
            clock_time = t2  # Network call fails at T2
            raise ProviderServerError("Failed at T2")

    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_max_queries_per_fixture=1,
    )
    fid = uuid.uuid4()
    session = AsyncMock()
    fixture = Fixture(
        id=fid,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=datetime.now(UTC),
    )
    home_team = Team(id=fixture.home_team_id, name="Arsenal")
    away_team = Team(id=fixture.away_team_id, name="Chelsea")
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock

    provider = MockFailingProvider()
    ctx = _make_context(settings=settings, session=session, provider=provider)

    sleep_called_with = []

    async def mock_sleeper(seconds: float):
        sleep_called_with.append(seconds)

    collector = ResearchCollector(sleeper=mock_sleeper, clock=clock)
    result = await collector.fetch(ctx, fixture_id=fid, phase=ForecastPhase.MORNING.value)

    assert result.normalized["status"] == ResearchState.PROVIDER_ERROR.value
    # Observation time must be T2, not T0!
    assert result.retrieved_at == t2
