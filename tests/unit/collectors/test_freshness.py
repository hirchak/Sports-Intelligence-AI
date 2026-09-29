from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        app_timezone="Europe/Warsaw",
        freshness_standings_seconds=12 * 3600,
        freshness_team_statistics_seconds=12 * 3600,
        freshness_odds_seconds=2 * 3600,
        freshness_prematch_odds_seconds=30 * 60,
    )


def test_none_captured_is_always_stale() -> None:
    policy = FreshnessPolicy(_settings())
    assert policy.is_stale(FreshnessCategory.STANDINGS, None, datetime.now(UTC))


def test_fresh_when_within_ttl() -> None:
    policy = FreshnessPolicy(_settings())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    captured = now - timedelta(hours=6)
    assert not policy.is_stale(FreshnessCategory.STANDINGS, captured, now)


def test_stale_when_past_ttl() -> None:
    policy = FreshnessPolicy(_settings())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    captured = now - timedelta(hours=13)
    assert policy.is_stale(FreshnessCategory.STANDINGS, captured, now)


def test_prematch_phase_uses_shorter_odds_ttl() -> None:
    policy = FreshnessPolicy(_settings())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    # 1 hour old — stale for PREMATCH (30m ttl) but fresh for MORNING (2h ttl).
    captured = now - timedelta(hours=1)
    assert policy.is_stale(FreshnessCategory.ODDS, captured, now, phase=ForecastPhase.PREMATCH)
    assert not policy.is_stale(FreshnessCategory.ODDS, captured, now, phase=ForecastPhase.MORNING)


def test_naive_datetime_is_normalized() -> None:
    policy = FreshnessPolicy(_settings())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    captured_naive = (now - timedelta(hours=6)).replace(tzinfo=None)
    assert not policy.is_stale(FreshnessCategory.STANDINGS, captured_naive, now)


def test_research_freshness_ttl() -> None:
    settings = _settings()
    settings.freshness_research_seconds = 6 * 3600
    settings.freshness_prematch_research_seconds = 90 * 60
    policy = FreshnessPolicy(settings)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    captured = now - timedelta(hours=2)
    assert not policy.is_stale(
        FreshnessCategory.RESEARCH, captured, now, phase=ForecastPhase.MORNING
    )
    assert policy.is_stale(FreshnessCategory.RESEARCH, captured, now, phase=ForecastPhase.PREMATCH)
