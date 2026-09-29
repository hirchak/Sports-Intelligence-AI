from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sports_intelligence.providers.search.base import (
    SearchResponse,
    SearchResultItem,
)


class MockSearchProvider:
    """Deterministic offline search provider for unit & integration testing."""

    name: str = "mock"

    def __init__(
        self,
        *,
        canned_results: dict[str, list[SearchResultItem]] | None = None,
        error_to_raise: Exception | None = None,
        default_results_count: int = 2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.canned_results: dict[str, list[SearchResultItem]] = canned_results or {}
        self.query_errors: dict[str, Exception] = {}
        self.error_to_raise = error_to_raise
        self.default_results_count = default_results_count
        self.calls: list[tuple[str, int]] = []
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def history(self) -> list[str]:
        return [call[0] for call in self.calls]

    def add_canned_response(self, query: str, results: list[SearchResultItem]) -> None:
        self.canned_results[query] = results

    def set_simulated_error(self, query: str, error: Exception) -> None:
        self.query_errors[query] = error

    def set_error(self, error: Exception | None) -> None:
        self.error_to_raise = error

    async def aclose(self) -> None:
        pass

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> SearchResponse:
        self.calls.append((query, max_results))
        if self.error_to_raise is not None:
            raise self.error_to_raise
        if query in self.query_errors:
            raise self.query_errors[query]

        now = self._clock()

        if query in self.canned_results:
            results = self.canned_results[query][:max_results]
            return SearchResponse(
                query=query,
                results=results,
                retrieved_at=now,
                cost_estimate=1,
                raw_payload={
                    "query": query,
                    "results": [
                        {
                            "url": r.url,
                            "domain": r.domain,
                            "title": r.title,
                            "content": r.content,
                            "score": r.score,
                            "published_at": r.published_at.isoformat() if r.published_at else None,
                            "retrieved_at": r.retrieved_at.isoformat() if r.retrieved_at else None,
                        }
                        for r in results
                    ],
                },
            )

        # Deterministic generation based on query tokens:
        q_lower = query.lower()
        items: list[SearchResultItem] = []

        if "injur" in q_lower:
            items.append(
                SearchResultItem(
                    url="https://theathletic.com/football/injury-update-latest",
                    domain="theathletic.com",
                    title="Premier League Injury News: Key starters doubtful ahead of weekend",
                    published_at=now - timedelta(hours=3),
                    retrieved_at=now,
                    content=(
                        "Manager confirmed star midfielder is ruled out with an ankle sprain. "
                        "Starting defender passed a late fitness test and will travel."
                    ),
                    score=0.92,
                    provider_metadata={"rank": 1, "topic": "news"},
                )
            )
            items.append(
                SearchResultItem(
                    url="https://bbc.com/sport/football/team-injuries-preview",
                    domain="bbc.com",
                    title="Team news and injury reports before kickoff",
                    published_at=now - timedelta(hours=5),
                    retrieved_at=now,
                    content="Key striker faces late fitness test after picking up a knock.",
                    score=0.88,
                    provider_metadata={"rank": 2, "topic": "news"},
                )
            )
            items.append(
                SearchResultItem(
                    url="https://skysports.com/football/squad-availability-digest",
                    domain="skysports.com",
                    title="Weekend Squad Availability Digest",
                    published_at=now - timedelta(hours=2),
                    retrieved_at=now,
                    content="Winger is sidelined with a hamstring issue and will not feature.",
                    score=0.84,
                    provider_metadata={"rank": 3, "topic": "news"},
                )
            )
        elif "press conference" in q_lower:
            items.append(
                SearchResultItem(
                    url="https://skysports.com/football/news/manager-press-conference",
                    domain="skysports.com",
                    title="Manager Press Conference: Tactical adjustments and rotation expected",
                    published_at=now - timedelta(hours=4),
                    retrieved_at=now,
                    content=(
                        "Head coach stated in pre-match press conference: 'We plan "
                        "significant rotation given the Champions League fixture.'"
                    ),
                    score=0.90,
                    provider_metadata={"rank": 1, "topic": "news"},
                )
            )
        elif "suspension" in q_lower:
            items.append(
                SearchResultItem(
                    url="https://premierleague.com/news/disciplinary-sanctions",
                    domain="premierleague.com",
                    title="Official Disciplinary Update: Yellow card accumulation suspension",
                    published_at=now - timedelta(days=1),
                    retrieved_at=now,
                    content="Starting center back will serve a one-match suspension.",
                    score=0.95,
                    provider_metadata={"rank": 1, "topic": "official"},
                )
            )
        elif "lineup" in q_lower:
            items.append(
                SearchResultItem(
                    url="https://guardian.com/football/predicted-lineups-weekend",
                    domain="guardian.com",
                    title="Predicted Lineups and Formation Analysis",
                    published_at=now - timedelta(hours=6),
                    retrieved_at=now,
                    content="Expected 4-3-3 formation with backup goalkeeper starting.",
                    score=0.85,
                    provider_metadata={"rank": 1, "topic": "news"},
                )
            )
        else:
            items.append(
                SearchResultItem(
                    url="https://sportsnews.example.com/fixture-preview-analysis",
                    domain="sportsnews.example.com",
                    title="Match Preview and Tactical Overview",
                    published_at=now - timedelta(hours=8),
                    retrieved_at=now,
                    content="Tactical breakdown and squad depth analysis for the fixture.",
                    score=0.75,
                    provider_metadata={"rank": 1, "topic": "general"},
                )
            )

        results = items[:max_results]
        return SearchResponse(
            query=query,
            results=results,
            retrieved_at=now,
            cost_estimate=1,
            raw_payload={
                "query": query,
                "results": [
                    {
                        "url": r.url,
                        "title": r.title,
                        "content": r.content,
                        "score": r.score,
                        "published_at": r.published_at.isoformat() if r.published_at else None,
                    }
                    for r in results
                ],
            },
            rate_limit_headers={"x-ratelimit-remaining": "999", "x-ratelimit-limit": "1000"},
        )
