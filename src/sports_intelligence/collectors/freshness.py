import hashlib
import json
import typing
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
            if category == FreshnessCategory.RESEARCH:
                return timedelta(seconds=self.settings.freshness_prematch_research_seconds)
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
        if category == FreshnessCategory.RESEARCH:
            return timedelta(seconds=self.settings.freshness_research_seconds)
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

    def to_dict(self) -> dict[str, int]:
        s = self.settings
        return {
            "freshness_standings_seconds": s.freshness_standings_seconds,
            "freshness_team_statistics_seconds": s.freshness_team_statistics_seconds,
            "freshness_team_form_seconds": s.freshness_team_form_seconds,
            "freshness_availability_seconds": s.freshness_availability_seconds,
            "freshness_lineups_seconds": s.freshness_lineups_seconds,
            "freshness_odds_seconds": s.freshness_odds_seconds,
            "freshness_prematch_odds_seconds": s.freshness_prematch_odds_seconds,
            "freshness_prematch_availability_seconds": s.freshness_prematch_availability_seconds,
            "freshness_research_seconds": s.freshness_research_seconds,
            "freshness_prematch_research_seconds": s.freshness_prematch_research_seconds,
        }

    def policy_fingerprint(self) -> str:
        data = self.to_dict()
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def compute_freshness_generation(self, evidence: "SelectedEvidence") -> str:
        """Deterministic representation of the current staleness state.

        When a source crosses from fresh to stale, this generation string changes,
        allowing the scanner to enqueue a new context build opportunity.
        """
        as_of_aware = (
            evidence.as_of.astimezone(UTC)
            if evidence.as_of.tzinfo
            else evidence.as_of.replace(tzinfo=UTC)
        )
        stale = []

        if evidence.standings is not None and self.is_stale(
            FreshnessCategory.STANDINGS,
            evidence.standings.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("standings")

        if evidence.home_team_stats is not None and self.is_stale(
            FreshnessCategory.TEAM_STATISTICS,
            evidence.home_team_stats.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("home_team_statistics")

        if evidence.away_team_stats is not None and self.is_stale(
            FreshnessCategory.TEAM_STATISTICS,
            evidence.away_team_stats.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("away_team_statistics")

        if evidence.home_form is not None and self.is_stale(
            FreshnessCategory.TEAM_FORM,
            evidence.home_form.as_of,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("home_team_form")

        if evidence.away_form is not None and self.is_stale(
            FreshnessCategory.TEAM_FORM,
            evidence.away_form.as_of,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("away_team_form")

        if evidence.home_availability is not None and self.is_stale(
            FreshnessCategory.AVAILABILITY,
            evidence.home_availability.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("home_availability")

        if evidence.away_availability is not None and self.is_stale(
            FreshnessCategory.AVAILABILITY,
            evidence.away_availability.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("away_availability")

        if evidence.odds_set is not None and self.is_stale(
            FreshnessCategory.ODDS,
            evidence.odds_set.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale.append("odds")

        if (
            evidence.research is not None
            and evidence.research.last_captured_at is not None
            and self.is_stale(
                FreshnessCategory.RESEARCH,
                evidence.research.last_captured_at,
                as_of_aware,
                evidence.forecast_phase,
            )
        ):
            stale.append("research")

        if evidence.forecast_phase != ForecastPhase.MORNING:
            if evidence.home_lineup is not None and self.is_stale(
                FreshnessCategory.LINEUPS,
                evidence.home_lineup.captured_at,
                as_of_aware,
                evidence.forecast_phase,
            ):
                stale.append("home_lineup")
            if evidence.away_lineup is not None and self.is_stale(
                FreshnessCategory.LINEUPS,
                evidence.away_lineup.captured_at,
                as_of_aware,
                evidence.forecast_phase,
            ):
                stale.append("away_lineup")

        if not stale:
            return "all_fresh"
        return "stale:" + ",".join(sorted(stale))


if typing.TYPE_CHECKING:
    from sports_intelligence.context.selector import SelectedEvidence
