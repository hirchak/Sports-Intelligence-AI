from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sports_intelligence.collectors.pre_match_scan import decide_categories
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        app_timezone="Europe/Warsaw",
        lineup_window_t_minutes=[120, 60, 20],
    )


def test_decide_categories_morning_when_kickoff_far() -> None:
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    kickoff = now + timedelta(hours=10)
    phase, categories = decide_categories(_settings(), kickoff_at=kickoff, now=now)
    assert phase is ForecastPhase.MORNING
    assert FreshnessCategory.STANDINGS in categories
    assert FreshnessCategory.TEAM_STATISTICS in categories
    assert FreshnessCategory.TEAM_FORM in categories
    assert FreshnessCategory.LINEUPS not in categories
    assert FreshnessCategory.AVAILABILITY not in categories


def test_decide_categories_prematch_starts_at_outermost_window() -> None:
    """M4.2 §2: PREMATCH begins exactly at the outermost T-window — no
    `max(window)+60` approximation. 180 min is MORNING now; 110 is
    PREMATCH."""
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    far = now + timedelta(minutes=180)
    phase, categories = decide_categories(_settings(), kickoff_at=far, now=now)
    assert phase is ForecastPhase.MORNING
    assert FreshnessCategory.LINEUPS not in categories

    close = now + timedelta(minutes=110)
    phase, categories = decide_categories(_settings(), kickoff_at=close, now=now)
    assert phase is ForecastPhase.PREMATCH
    assert FreshnessCategory.LINEUPS in categories
    assert FreshnessCategory.AVAILABILITY in categories
    assert FreshnessCategory.ODDS in categories


def test_execute_plan_skips_standings_and_team_stats_without_season() -> None:
    """M4.4 §2: automated plan skips standings and team_stats when season_id is None."""
    import asyncio
    from unittest.mock import MagicMock

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision, execute_plan

    enqueued: list[tuple[str, dict[str, object]]] = []

    async def fake_enqueue(name: str, **kwargs: object) -> None:
        enqueued.append((name, kwargs))

    decision_without_season = PreMatchDecision(
        fixture_id="fix-1",
        league_id="lg-1",
        home_team_id="tm-1",
        away_team_id="tm-2",
        season_id=None,
        kickoff_at=datetime.now(UTC),
        phase=ForecastPhase.PREMATCH,
        categories_to_collect=(
            FreshnessCategory.STANDINGS,
            FreshnessCategory.TEAM_STATISTICS,
            FreshnessCategory.AVAILABILITY,
        ),
    )

    ctx = MagicMock()
    settings = _settings()
    counters = asyncio.run(
        execute_plan(
            settings, ctx, decisions=[decision_without_season], enqueue_collector=fake_enqueue
        )
    )
    assert "standings" not in counters
    assert "team_stats" not in counters
    assert "availability" in counters
    names = [name for name, _ in enqueued]
    assert "standings" not in names
    assert "team_stats" not in names
    assert "availability" in names

    # With season_id, all are enqueued:
    enqueued.clear()
    decision_with_season = PreMatchDecision(
        fixture_id="fix-2",
        league_id="lg-1",
        home_team_id="tm-1",
        away_team_id="tm-2",
        season_id="sea-1",
        kickoff_at=datetime.now(UTC),
        phase=ForecastPhase.PREMATCH,
        categories_to_collect=(
            FreshnessCategory.STANDINGS,
            FreshnessCategory.TEAM_STATISTICS,
            FreshnessCategory.AVAILABILITY,
        ),
    )
    counters2 = asyncio.run(
        execute_plan(
            settings, ctx, decisions=[decision_with_season], enqueue_collector=fake_enqueue
        )
    )
    assert counters2["standings"] == 1
    assert counters2["team_stats"] == 2
    assert counters2["availability"] == 2
