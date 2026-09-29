from __future__ import annotations

from datetime import datetime

from sports_intelligence.core.phases import ForecastPhase


def build_research_queries(
    *,
    home_team_name: str,
    away_team_name: str,
    kickoff_at: datetime,
    phase: ForecastPhase = ForecastPhase.MORNING,
    max_queries: int = 6,
) -> list[str]:
    """Generate deterministic, bounded search queries for pre-match research.

    Targets key pre-match informational families:
    - injuries & fitness issues;
    - manager statements & press conferences;
    - disciplinary suspensions;
    - probable lineup & tactical news;
    - fixture team news.
    """
    date_str = kickoff_at.strftime("%Y-%m-%d")
    h_clean = home_team_name.strip()
    a_clean = away_team_name.strip()

    if phase == ForecastPhase.PREMATCH:
        # Pre-match refresh prioritizes immediate lineup / late fitness news:
        candidates = [
            f"{h_clean} lineup {a_clean} {date_str}",
            f"{a_clean} lineup {h_clean} {date_str}",
            f"{h_clean} injuries {date_str}",
            f"{a_clean} injuries {date_str}",
            f"{h_clean} vs {a_clean} team news {date_str}",
            f"{h_clean} manager press conference {a_clean}",
        ]
    else:
        # Morning scan targets broad preparation context:
        candidates = [
            f"{h_clean} injuries {date_str}",
            f"{a_clean} injuries {date_str}",
            f"{h_clean} manager press conference {a_clean}",
            f"{h_clean} suspension",
            f"{a_clean} suspension",
            f"{h_clean} vs {a_clean} team news {date_str}",
        ]

    limit = max(1, max_queries)
    return candidates[:limit]
