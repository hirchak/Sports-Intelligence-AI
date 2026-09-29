from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchResultItem:
    url: str
    domain: str
    title: str
    content: str = ""
    published_at: datetime | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    score: float | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        url: str,
        domain: str,
        title: str,
        content: str = "",
        published_at: datetime | None = None,
        retrieved_at: datetime | None = None,
        score: float | None = None,
        provider_metadata: dict[str, Any] | None = None,
        *,
        snippet: str | None = None,
        relevance_score: float | None = None,
    ) -> None:
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "content", snippet if snippet is not None else content)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(
            self,
            "retrieved_at",
            retrieved_at if retrieved_at is not None else datetime.now(UTC),
        )
        object.__setattr__(
            self,
            "score",
            relevance_score if relevance_score is not None else score,
        )
        object.__setattr__(self, "provider_metadata", provider_metadata or {})

    @property
    def snippet(self) -> str:
        return self.content

    @property
    def relevance_score(self) -> float | None:
        return self.score


@dataclass(frozen=True)
class SearchResponse:
    query: str
    results: list[SearchResultItem]
    retrieved_at: datetime
    cost_estimate: int = 1
    raw_payload: dict[str, Any] | None = None
    rate_limit_headers: dict[str, str] | None = None

    @property
    def quota_headers(self) -> dict[str, str]:
        return self.rate_limit_headers or {}


@runtime_checkable
class SearchProvider(Protocol):
    """Provider-independent search boundary."""

    name: str

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> SearchResponse: ...

    async def aclose(self) -> None: ...
