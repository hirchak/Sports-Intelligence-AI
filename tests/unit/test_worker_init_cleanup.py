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
