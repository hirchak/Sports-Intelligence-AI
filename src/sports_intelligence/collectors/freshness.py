from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory


@dataclass(frozen=True)
class FreshnessPolicy:
    """Per-category, per-phase configurable freshness policy.

    The policy is a pure function of Settings so all decisions are
    deterministic and unit-testable without any database access.
    """

    settings: Settings

    def ttl_for(self, category: FreshnessCategory, phase: ForecastPhase) -> timedelta:
        if phase == ForecastPhase.PREMATCH:
            if category == FreshnessCategory.AVAILABILITY:
                return timedelta(seconds=self.settings.freshness_prematch_availability_seconds)
            if category == FreshnessCategory.ODDS:
                return timedelta(seconds=self.settings.freshness_prematch_odds_seconds)
            if category == FreshnessCategory.LINEUPS:
                return timedelta(seconds=self.settings.freshness_lineups_seconds)
        if category == FreshnessCategory.STANDINGS:
            return timedelta(seconds=self.settings.freshness_standings_seconds)
        if category == FreshnessCategory.TEAM_STATISTICS:
            return timedelta(seconds=self.settings.freshness_team_statistics_seconds)
        if category == FreshnessCategory.TEAM_FORM:
            return timedelta(seconds=self.settings.freshness_team_form_seconds)
        if category == FreshnessCategory.AVAILABILITY:
            return timedelta(seconds=self.settings.freshness_availability_seconds)
        if category == FreshnessCategory.LINEUPS:
            return timedelta(seconds=self.settings.freshness_lineups_seconds)
        if category == FreshnessCategory.ODDS:
            return timedelta(seconds=self.settings.freshness_odds_seconds)
        return timedelta(hours=1)

    def is_stale(
        self,
        category: FreshnessCategory,
        last_retrieved_at: datetime | None,
        now: datetime,
        phase: ForecastPhase = ForecastPhase.MORNING,
    ) -> bool:
        """`None` retrieved_at is always stale (spec 14 §7 UNKNOWN ≠ fresh)."""
        if last_retrieved_at is None:
            return True
        if last_retrieved_at.tzinfo is None:
            last_retrieved_at = last_retrieved_at.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return (now - last_retrieved_at) > self.ttl_for(category, phase)
