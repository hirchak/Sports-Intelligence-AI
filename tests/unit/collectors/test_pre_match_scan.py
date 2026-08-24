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


def test_decide_categories_prematch_when_close_to_window() -> None:
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    kickoff = now + timedelta(minutes=180)
    phase, categories = decide_categories(_settings(), kickoff_at=kickoff, now=now)
    assert phase is ForecastPhase.PREMATCH
    assert FreshnessCategory.LINEUPS in categories
    assert FreshnessCategory.AVAILABILITY in categories
    assert FreshnessCategory.ODDS in categories
