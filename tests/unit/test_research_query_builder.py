from __future__ import annotations

from datetime import UTC, datetime

from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.research.query_builder import build_research_queries


def test_build_research_queries_morning_phase() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    queries = build_research_queries(
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
        max_queries=5,
    )

    assert len(queries) <= 5
    assert len(queries) > 0
    # Determinism: same input produces exact same list
    queries2 = build_research_queries(
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
        max_queries=5,
    )
    assert queries == queries2
    assert any("Arsenal" in q for q in queries)
    assert any("Chelsea" in q for q in queries)


def test_build_research_queries_prematch_phase() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    queries = build_research_queries(
        home_team_name="Real Madrid",
        away_team_name="Barcelona",
        kickoff_at=kickoff,
        phase=ForecastPhase.PREMATCH,
        max_queries=4,
    )

    assert len(queries) <= 4
    # Pre-match queries emphasize lineup and confirmed news
    assert any("lineup" in q.lower() or "team news" in q.lower() for q in queries)


def test_build_research_queries_caps_to_max() -> None:
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    queries = build_research_queries(
        home_team_name="Liverpool",
        away_team_name="Manchester City",
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
        max_queries=2,
    )
    assert len(queries) == 2
