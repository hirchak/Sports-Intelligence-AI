from __future__ import annotations

import pytest

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import ProviderConfigError


class FailingConnection:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")

    async def __aenter__(self) -> FailingConnection:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class TrackingEngine:
    def __init__(self) -> None:
        self.disposed = False

    def connect(self) -> FailingConnection:
        return FailingConnection()

    async def dispose(self) -> None:
        self.disposed = True


async def test_worker_init_failure_disposes_engine_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sports_intelligence.core.league_config import LeagueConfig
    from sports_intelligence.workers.tasks import sports as sports_tasks

    monkeypatch.setattr(
        sports_tasks,
        "get_settings",
        lambda: Settings(_env_file=None, app_env="mock", sports_provider="unknown-typo"),
    )
    monkeypatch.setattr(
        sports_tasks,
        "load_league_config",
        lambda path: LeagueConfig(version=1, leagues=[]),
    )
    tracking_engine = TrackingEngine()
    monkeypatch.setattr(sports_tasks, "create_engine", lambda url: tracking_engine)

    with pytest.raises(ProviderConfigError):
        await sports_tasks._run_discovery("job-1", "2026-08-21", 1, "Europe/Warsaw")

    assert tracking_engine.disposed is True


class TrackingSearchProvider:
    name = "mock"

    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["success", "quota_denied", "provider_error", "persist_failure"],
)
async def test_run_collect_job_always_closes_search_provider(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    """Regression for M5.1 §5: SearchProvider must always be closed in finally,
    and unrelated providers must not be instantiated for research jobs.
    """
    import uuid
    from unittest.mock import AsyncMock, MagicMock

    from sports_intelligence.collectors.quota import QuotaUnavailableError
    from sports_intelligence.workers.tasks import collect as collect_tasks

    tracking_provider = TrackingSearchProvider()
    sports_provider_mock = MagicMock()
    odds_provider_mock = MagicMock()

    monkeypatch.setattr(
        collect_tasks,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            app_env="mock",
            search_provider="mock",
            research_enabled=True,
            database_url="postgresql+asyncpg://mock/db",
            redis_url="redis://mock/0",
        ),
    )
    monkeypatch.setattr(collect_tasks, "build_search_provider", lambda _: tracking_provider)
    monkeypatch.setattr(collect_tasks, "build_sports_provider", sports_provider_mock)
    monkeypatch.setattr(collect_tasks, "build_odds_provider", odds_provider_mock)

    # Mock engine, session factory, redis
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    monkeypatch.setattr(collect_tasks, "create_engine", lambda _: mock_engine)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock()
    monkeypatch.setattr(collect_tasks, "create_session_factory", lambda _: mock_factory)

    mock_redis = MagicMock()
    mock_redis.aclose = AsyncMock()
    monkeypatch.setattr(collect_tasks.Redis, "from_url", lambda _: mock_redis)
    monkeypatch.setattr(collect_tasks, "update_job_status", AsyncMock())
    monkeypatch.setattr(collect_tasks, "record_job_attempt", AsyncMock())

    # Scenario setup
    if scenario == "success":
        ref_mock = MagicMock(
            snapshot_id=uuid.uuid4(),
            captured_at=MagicMock(isoformat=lambda: "2026-08-21T00:00:00Z"),
        )
        monkeypatch.setattr(collect_tasks, "run_collector", AsyncMock(return_value=ref_mock))
        await collect_tasks._run_collect_job(
            job_id=str(uuid.uuid4()),
            collector_name="research",
            inputs_json='{"fixture_id": "123"}',
            phase="morning",
            estimated_cost=1,
        )
    elif scenario == "quota_denied":
        monkeypatch.setattr(
            collect_tasks,
            "run_collector",
            AsyncMock(side_effect=QuotaUnavailableError("Quota denied")),
        )
        with pytest.raises(QuotaUnavailableError):
            await collect_tasks._run_collect_job(
                job_id=str(uuid.uuid4()),
                collector_name="research",
                inputs_json='{"fixture_id": "123"}',
                phase="morning",
                estimated_cost=1,
            )
    elif scenario == "provider_error":
        monkeypatch.setattr(
            collect_tasks, "run_collector", AsyncMock(side_effect=RuntimeError("Search API failed"))
        )
        with pytest.raises(RuntimeError):
            await collect_tasks._run_collect_job(
                job_id=str(uuid.uuid4()),
                collector_name="research",
                inputs_json='{"fixture_id": "123"}',
                phase="morning",
                estimated_cost=1,
            )
    elif scenario == "persist_failure":
        monkeypatch.setattr(
            collect_tasks,
            "run_collector",
            AsyncMock(side_effect=RuntimeError("DB persistence failure")),
        )
        with pytest.raises(RuntimeError):
            await collect_tasks._run_collect_job(
                job_id=str(uuid.uuid4()),
                collector_name="research",
                inputs_json='{"fixture_id": "123"}',
                phase="morning",
                estimated_cost=1,
            )

    # Assertions:
    # 1. Search provider is ALWAYS closed
    assert tracking_provider.closed is True, f"SearchProvider was not closed in scenario {scenario}"
    # 2. Unrelated providers are NEVER instantiated for research jobs
    assert sports_provider_mock.called is False
    assert odds_provider_mock.called is False
