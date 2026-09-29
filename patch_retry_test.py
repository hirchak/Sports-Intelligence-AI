with open("tests/unit/test_search_provider.py") as f:
    content = f.read()

old_test = """@pytest.mark.asyncio
async def test_retry_per_attempt_quota_reservation() -> None:
    from sports_intelligence.collectors.research_collector import ResearchCollector
    from sports_intelligence.providers.errors import ProviderServerError
    from sports_intelligence.collectors.framework import CollectorContext
    from tests.unit.conftest import MockQuotaLedger
    from sports_intelligence.providers.search.base import SearchResponse
    import uuid

    class MockSearchFailFirst:
        name = "mock"
        def __init__(self):
            self.calls = 0
            
        async def search(self, query: str, **kwargs) -> SearchResponse:
            self.calls += 1
            if self.calls == 1:
                raise ProviderServerError("Failed first time")
            return SearchResponse(
                query=query,
                results=[],
                retrieved_at=datetime.now(UTC),
                cost_estimate=1,
                raw_payload={}
            )

    provider = MockSearchFailFirst()
    quota = MockQuotaLedger()
    
    # We need a context and a fixture, but this is a unit test so we might just 
    # test the quota reserve counting. Wait, actually `fetch` requires a db session 
    # and a valid fixture. Let me do this via a mock session or similar, or I can 
    # test the retry loop inside the collector if I mock `build_research_queries`.
"""

new_test = """@pytest.mark.asyncio
async def test_retry_per_attempt_quota_reservation() -> None:
    from sports_intelligence.collectors.research_collector import ResearchCollector
    from sports_intelligence.providers.errors import ProviderServerError
    from sports_intelligence.collectors.framework import CollectorContext
    from sports_intelligence.providers.search.base import SearchResponse, SearchProvider
    from sports_intelligence.core.config import Settings
    from sports_intelligence.db.models import Fixture, Team
    from sports_intelligence.core.phases import ForecastPhase
    import uuid
    from unittest.mock import AsyncMock, MagicMock

    class MockSearchFailFirst(SearchProvider):
        name = "mock"
        def __init__(self):
            self.calls = 0
            
        async def search(self, query: str, **kwargs) -> SearchResponse:
            self.calls += 1
            if self.calls == 1:
                raise ProviderServerError("Failed first time")
            return SearchResponse(
                query=query,
                results=[],
                retrieved_at=datetime.now(UTC),
                cost_estimate=1,
                raw_payload={},
                rate_limit_headers={}
            )

    provider = MockSearchFailFirst()
    
    lock_mgr = MagicMock()
    lock_mgr.acquire = AsyncMock(return_value=True)
    lock_mgr.release = AsyncMock()

    quota_mgr = MagicMock()
    allowed_decision = MagicMock(denied=False, allowed=True, reason="ok")
    quota_mgr.reserve = AsyncMock(return_value=allowed_decision)
    quota_mgr.record_success = AsyncMock()
    quota_mgr.record_failure = AsyncMock()
    
    settings = Settings(_env_file=None, app_env="mock", search_provider="mock", research_enabled=True, research_max_queries_per_fixture=1)
    session = AsyncMock()
    fixture = Fixture(id=uuid.uuid4(), home_team_id=uuid.uuid4(), away_team_id=uuid.uuid4(), kickoff_at=datetime.now(UTC))
    home_team = Team(id=uuid.uuid4(), name="Arsenal")
    away_team = Team(id=uuid.uuid4(), name="Chelsea")
    row_mock = MagicMock()
    row_mock.first.return_value = (fixture, home_team, away_team)
    session.execute.return_value = row_mock
    
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock()
    
    ctx = CollectorContext(
        settings=settings,
        session_factory=session_factory,
        redis=MagicMock(),
        locks=lock_mgr,
        quota=quota_mgr,
        freshness=MagicMock(),
        provider=provider,
    )
    
    collector = ResearchCollector()
    await collector.fetch(ctx, fixture_id=fixture.id, phase=ForecastPhase.MORNING.value)
    
    assert provider.calls == 2
    assert quota_mgr.reserve.call_count == 2
    assert quota_mgr.record_failure.call_count == 1
    assert quota_mgr.record_success.call_count == 1
"""

content = content.replace(old_test, new_test)

with open("tests/unit/test_search_provider.py", "w") as f:
    f.write(content)

