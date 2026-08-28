from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from sports_intelligence.collectors.framework import (
    CollectorContext,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.core.config import Settings
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory
from sports_intelligence.core.time import utc_window_for_local_day
from sports_intelligence.db.models import Fixture, League, Team


@dataclass(frozen=True)
class PreMatchDecision:
    fixture_id: str
    league_id: str
    home_team_id: str
    away_team_id: str
    season_id: str | None
    kickoff_at: datetime
    phase: ForecastPhase
    categories_to_collect: tuple[FreshnessCategory, ...]


async def select_upcoming_fixtures(
    session: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime | None = None,
    limit: int = 200,
) -> list[tuple[Fixture, League, Team, Team]]:
    HomeTeam = aliased(Team, name="home_team")
    AwayTeam = aliased(Team, name="away_team")
    conditions = [
        League.enabled == True,  # noqa: E712
        Fixture.kickoff_at >= window_start,
        Fixture.kickoff_at <= window_end,
    ]
    if now is not None:
        # Only future / not-yet-started fixtures (M4.1 §4).
        conditions.append(Fixture.kickoff_at > now)
    stmt = (
        select(Fixture, League, HomeTeam, AwayTeam)
        .join(League, League.id == Fixture.league_id)
        .join(HomeTeam, HomeTeam.id == Fixture.home_team_id)
        .join(AwayTeam, AwayTeam.id == Fixture.away_team_id)
        .where(*conditions)
        .order_by(Fixture.kickoff_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(fixture, league, home, away) for fixture, league, home, away in rows]


def decide_categories(
    settings: Settings,
    *,
    kickoff_at: datetime,
    now: datetime,
) -> tuple[ForecastPhase, tuple[FreshnessCategory, ...]]:
    """Pick the phase and the categories worth collecting (M4.2 §2).

    PREMATCH begins exactly at the outermost configured T-window
    (max(lineup_window_t_minutes)) — no `+60` approximation. Inside
    PREMATCH, lineups/availability/odds are collected; the per-window
    enforcement (T-120 → T-60 → T-20) happens at execution time via the
    refresh-opportunity identity and the lineup window policy.
    MORNING otherwise (standings, team stats, form inputs).
    """
    delta = kickoff_at - now
    minutes_until = delta.total_seconds() / 60.0

    windows = [w for w in settings.lineup_window_t_minutes if w > 0]
    prematch_horizon = max(windows) if windows else 60

    if minutes_until <= prematch_horizon:
        phase = ForecastPhase.PREMATCH
        categories: tuple[FreshnessCategory, ...] = (
            FreshnessCategory.STANDINGS,
            FreshnessCategory.TEAM_STATISTICS,
            FreshnessCategory.TEAM_FORM,
            FreshnessCategory.AVAILABILITY,
            FreshnessCategory.LINEUPS,
            FreshnessCategory.ODDS,
        )
        return phase, categories

    phase = ForecastPhase.MORNING
    categories = (
        FreshnessCategory.STANDINGS,
        FreshnessCategory.TEAM_STATISTICS,
        FreshnessCategory.TEAM_FORM,
    )
    return phase, categories


async def plan_for_date(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    day: date,
    now: datetime | None = None,
) -> list[PreMatchDecision]:
    """Read DB and decide which collectors to enqueue for a given
    Warsaw calendar day.

    - window boundaries are the Warsaw local-midnight → UTC conversions
      (`utc_window_for_local_day`), so the scan covers the full local
      day across DST transitions;
    - only future/not-started fixtures are considered;
    - disabled leagues (YAML config) are skipped.
    """
    now = now or datetime.now(UTC).replace(tzinfo=UTC)
    window_start, window_end = utc_window_for_local_day(day, settings.app_timezone)
    league_config = load_league_config(settings.leagues_config_path)
    enabled_by_id: dict[str, object] = {str(slug): True for slug in league_config.enabled_slugs()}
    async with session_factory() as session:
        rows = await select_upcoming_fixtures(
            session,
            window_start=window_start,
            window_end=window_end,
            now=now,
        )
    decisions: list[PreMatchDecision] = []
    for fixture, league, home, away in rows:
        if str(league.slug) not in enabled_by_id:
            continue
        phase, categories = decide_categories(settings, kickoff_at=fixture.kickoff_at, now=now)
        decisions.append(
            PreMatchDecision(
                fixture_id=str(fixture.id),
                league_id=str(league.id),
                home_team_id=str(home.id),
                away_team_id=str(away.id),
                season_id=str(fixture.season_id) if fixture.season_id is not None else None,
                kickoff_at=fixture.kickoff_at,
                phase=phase,
                categories_to_collect=categories,
            )
        )
    return decisions


def is_stale_for_decision(
    policy: FreshnessPolicy,
    decision: PreMatchDecision,
    *,
    last_captured: datetime | None,
    now: datetime,
) -> bool:
    """Aggregate staleness across the decision's categories.

    Conservative: any stale category triggers a refresh (caller
    decides individual collector enqueues, but the framework
    short-circuits per-collector under its own freshness lock).
    """
    if last_captured is None:
        return True
    for category in decision.categories_to_collect:
        if policy.is_stale(category, last_captured, now, decision.phase):
            return True
    return False


async def execute_plan(
    settings: Settings,
    ctx: CollectorContext,
    *,
    decisions: list[PreMatchDecision],
    enqueue_collector: Any,
) -> dict[str, int]:
    """Walk a plan and dispatch collector jobs.

    `enqueue_collector(name, **inputs)` is provided by the caller
    (Celery `apply_async` in production; in-memory queue in tests).
    Every enqueue carries the decision's phase so the collector worker
    executes under the SAME freshness phase (PREMATCH values actually
    applied). Returns a counter of enqueues by category.
    """
    counters: dict[str, int] = {}
    for decision in decisions:
        phase = decision.phase.value
        # Standings / team_stats are per-league / per-team; the
        # framework + Redis lock layer deduplicates across fixtures.
        if FreshnessCategory.STANDINGS in decision.categories_to_collect:
            await enqueue_collector(
                "standings",
                league_id=decision.league_id,
                season_id=decision.season_id,
                phase=phase,
            )
            counters["standings"] = counters.get("standings", 0) + 1
        if FreshnessCategory.TEAM_STATISTICS in decision.categories_to_collect:
            for team_id in (decision.home_team_id, decision.away_team_id):
                await enqueue_collector(
                    "team_stats",
                    team_id=team_id,
                    league_id=decision.league_id,
                    season_id=decision.season_id,
                    phase=phase,
                )
            counters["team_stats"] = counters.get("team_stats", 0) + 2
        if FreshnessCategory.AVAILABILITY in decision.categories_to_collect:
            for team_id in (decision.home_team_id, decision.away_team_id):
                await enqueue_collector(
                    "availability",
                    fixture_id=decision.fixture_id,
                    team_id=team_id,
                    phase=phase,
                )
            counters["availability"] = counters.get("availability", 0) + 2
        if FreshnessCategory.LINEUPS in decision.categories_to_collect:
            for team_id in (decision.home_team_id, decision.away_team_id):
                await enqueue_collector(
                    "lineups",
                    fixture_id=decision.fixture_id,
                    team_id=team_id,
                    phase=phase,
                )
            counters["lineups"] = counters.get("lineups", 0) + 2
        if FreshnessCategory.ODDS in decision.categories_to_collect:
            await enqueue_collector(
                "odds",
                fixture_id=decision.fixture_id,
                league_id=decision.league_id,
                phase=phase,
            )
            counters["odds"] = counters.get("odds", 0) + 1
    return counters
