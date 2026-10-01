"""Scheduled discovery wrapper execution tests (M4.1 §1).

`Beat` targets `sports.schedule_discovery(slot)` — an argument-free
wrapper. These tests run the task body EAGERLY and prove it creates a
proper Job row and enqueues the full immutable discovery execution tuple,
and that morning ≠ refresh identities (the 13:00 refresh is NOT
suppressed by the successful 09:00 run).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sports_intelligence.core.config import Settings
from sports_intelligence.core.league_config import LeagueConfig
from sports_intelligence.workers.tasks.scheduling import SCHEDULE_SLOTS, _run_schedule


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> MagicMock:
        return MagicMock()


class _FakeFactory:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSession:  # type: ignore[no-untyped-def]
        session = _FakeSession()
        self.sessions.append(session)
        return session


def _patched_context(fake_factory: _FakeFactory):
    return (
        patch(
            "sports_intelligence.workers.tasks.scheduling.create_session_factory",
            return_value=fake_factory,
        ),
        patch(
            "sports_intelligence.workers.tasks.scheduling.create_engine",
            return_value=MagicMock(dispose=AsyncMock()),
        ),
        patch(
            "sports_intelligence.workers.tasks.scheduling.load_league_config",
            return_value=LeagueConfig(version=3, leagues=[]),
        ),
    )


@pytest.mark.asyncio
async def test_schedule_morning_creates_job_and_enqueues_full_tuple() -> None:
    fake_factory = _FakeFactory()
    captured: list[list[object]] = []

    async def _fake_enqueue(
        task, *, job_id, fixture_date, expected_league_config_version, discovery_timezone
    ):
        captured.append([job_id, fixture_date, expected_league_config_version, discovery_timezone])

    async def _fake_create_job(session, job_type, idempotency_key, scheduled_for):
        return _FakeJob("11111111-2222-3333-4444-555555555555"), True

    ctxs = _patched_context(fake_factory)
    with ctxs[0], ctxs[1], ctxs[2]:
        from sports_intelligence.workers.tasks import scheduling as mod

        with (
            patch.object(mod, "_enqueue", _fake_enqueue),
            patch.object(mod, "create_or_get_job", _fake_create_job),
            patch.object(mod, "update_job_status", AsyncMock()),
            patch.object(
                mod,
                "get_settings",
                return_value=Settings(_env_file=None, app_timezone="Europe/Warsaw"),
            ),
            patch.object(mod, "datetime", wraps=datetime) as clock,
        ):
            # The UTC runner is still on Aug 21; configured Warsaw is already Aug 22.
            clock.now.return_value = datetime(2026, 8, 21, 22, 30, tzinfo=UTC)
            result = await _run_schedule("morning")

    assert result["slot"] == "morning"
    assert result["created"] is True
    assert result["fixture_date"] == "2026-08-22"
    assert result["config_version"] == 3
    assert len(captured) == 1
    args = captured[0]
    assert len(args) == 4
    assert args[0] == "11111111-2222-3333-4444-555555555555"
    assert args[1] == result["fixture_date"]
    assert args[2] == 3
    assert args[3] == "Europe/Warsaw"


@pytest.mark.asyncio
async def test_morning_and_refresh_are_distinct_jobs() -> None:
    """The 13:00 refresh creates a DIFFERENT job than the 09:00 morning
    run (distinct idempotency keys); morning success never suppresses it."""
    fake_factory = _FakeFactory()
    keys: list[str] = []

    async def _fake_create_job(session, job_type, idempotency_key, scheduled_for):
        keys.append(idempotency_key)
        return _FakeJob(idempotency_key), True

    ctxs = _patched_context(fake_factory)
    with ctxs[0], ctxs[1], ctxs[2]:
        from sports_intelligence.workers.tasks import scheduling as mod

        with (
            patch.object(mod, "_enqueue", AsyncMock()),
            patch.object(mod, "create_or_get_job", _fake_create_job),
            patch.object(mod, "update_job_status", AsyncMock()),
        ):
            await _run_schedule("morning")
            await _run_schedule("refresh")

    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert ":morning:" in keys[0]
    assert ":refresh:" in keys[1]


@pytest.mark.asyncio
async def test_unknown_slot_rejected() -> None:
    assert SCHEDULE_SLOTS == ("morning", "refresh")
    fake_factory = _FakeFactory()
    ctxs = _patched_context(fake_factory)
    with ctxs[0], ctxs[1], ctxs[2], pytest.raises(ValueError):
        await _run_schedule("midnight")


@pytest.mark.asyncio
async def test_enqueue_failure_marks_job_failed() -> None:
    fake_factory = _FakeFactory()
    status_calls: list[str] = []

    async def _boom_enqueue(*_args, **_kwargs):
        raise RuntimeError("broker down")

    async def _fake_update(session, job_id, status):
        status_calls.append(status.value)

    async def _fake_create(session, job_type, idempotency_key, scheduled_for):
        return _FakeJob("22222222-2222-2222-2222-222222222222"), True

    ctxs = _patched_context(fake_factory)
    with ctxs[0], ctxs[1], ctxs[2]:
        from sports_intelligence.workers.tasks import scheduling as mod

        with (
            patch.object(mod, "_enqueue", _boom_enqueue),
            patch.object(mod, "create_or_get_job", _fake_create),
            patch.object(mod, "update_job_status", _fake_update),
            pytest.raises(RuntimeError),
        ):
            await _run_schedule("morning")
    assert "FAILED" in status_calls
