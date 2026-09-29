from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from sports_intelligence.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)
from sports_intelligence.providers.search.base import SearchResultItem
from sports_intelligence.providers.search.mock import MockSearchProvider
from sports_intelligence.providers.search.tavily import TavilySearchProvider


@pytest.mark.asyncio
async def test_mock_search_provider_deterministic_results() -> None:
    provider = MockSearchProvider()
    response = await provider.search("Arsenal injury update", max_results=3)

    assert response.query == "Arsenal injury update"
    assert len(response.results) == 3
    assert all(isinstance(r, SearchResultItem) for r in response.results)
    assert any("Injury" in r.title for r in response.results)
    assert response.results[0].relevance_score is not None
    assert response.results[0].relevance_score >= response.results[1].relevance_score
    assert len(provider.history) == 1


@pytest.mark.asyncio
async def test_mock_search_provider_canned_responses() -> None:
    provider = MockSearchProvider()
    canned_item = SearchResultItem(
        url="https://example.com/custom",
        title="Custom News",
        snippet="Custom snippet text",
        published_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        domain="example.com",
        relevance_score=0.95,
    )
    provider.add_canned_response("custom query", [canned_item])

    resp = await provider.search("custom query")
    assert len(resp.results) == 1
    assert resp.results[0].url == "https://example.com/custom"


@pytest.mark.asyncio
async def test_mock_search_provider_simulated_error() -> None:
    provider = MockSearchProvider()
    provider.set_simulated_error("error_query", ProviderRateLimitError("Rate limit reached"))

    with pytest.raises(ProviderRateLimitError):
        await provider.search("error_query")


@pytest.mark.asyncio
async def test_tavily_search_provider_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["api_key"] == "secret-key-123"
        assert data["query"] == "Chelsea vs Arsenal injuries"
        payload = {
            "query": data["query"],
            "results": [
                {
                    "title": "Arsenal Injury News",
                    "url": "https://www.arsenal.com/news/injuries?utm_source=twitter",
                    "content": "Martin Odegaard has returned to full training.",
                    "score": 0.88,
                    "published_date": "2026-08-21T09:30:00Z",
                    "id": "tav-item-1",
                },
                {
                    "title": "Chelsea Team News",
                    "url": "https://www.chelseafc.com/en/news/article/update",
                    "content": "Reece James is sidelined with a hamstring injury.",
                    "score": 0.82,
                    "published_date": "Sat, 22 Aug 2026 00:00:00 GMT",
                    "id": "tav-item-2",
                },
            ],
        }
        headers = {
            "x-ratelimit-remaining-requests": "95",
            "x-ratelimit-remaining-tokens": "95000",
        }
        return httpx.Response(200, json=payload, headers=headers)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client)

    try:
        response = await provider.search("Chelsea vs Arsenal injuries", max_results=5)
        assert response.query == "Chelsea vs Arsenal injuries"
        assert len(response.results) == 2
        first = response.results[0]
        assert first.title == "Arsenal Injury News"
        # URL tracking params stripped in normalization
        assert "utm_source" not in first.url
        assert first.domain == "arsenal.com"
        assert first.published_at == datetime(2026, 8, 21, 9, 30, tzinfo=UTC)
        assert first.relevance_score == 0.88
        assert first.provider_metadata.get("tavily_id") == "tav-item-1"
        assert first.provider_metadata.get("rank") == 1

        second = response.results[1]
        assert second.published_at == datetime(2026, 8, 22, 0, 0, tzinfo=UTC)
        assert second.provider_metadata.get("tavily_id") == "tav-item-2"
        assert second.provider_metadata.get("rank") == 2
        assert response.quota_headers.get("x-ratelimit-remaining-requests") == "95"
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_tavily_search_provider_401_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="wrong-key", client=client)

    try:
        with pytest.raises(ProviderAuthError):
            await provider.search("any query")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_tavily_search_provider_429_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Rate limit exceeded"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client)

    try:
        with pytest.raises(ProviderRateLimitError):
            await provider.search("any query")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_tavily_search_provider_500_retries_and_raises_transient() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "Internal server error"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client, max_retries=2)

    try:
        with pytest.raises(ProviderServerError):
            await provider.search("any query")
        assert call_count == 3
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_tavily_search_provider_timeout_raises_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client, max_retries=1)

    try:
        with pytest.raises(ProviderTimeoutError):
            await provider.search("any query")
    finally:
        await provider.aclose()


def test_tavily_search_provider_secret_not_leaked() -> None:
    api_key = "super_secret_tavily_key_xyz987"
    provider = TavilySearchProvider(api_key=api_key)
    repr_str = repr(provider)
    str_str = str(provider)

    assert api_key not in repr_str
    assert api_key not in str_str


@pytest.mark.asyncio
async def test_tavily_retrieval_time_captured_after_response_anti_leakage() -> None:
    """Regression for M5.1: request starts before as_of, response completes after as_of.

    Proves retrieved_at represents response observation time, not dispatch time,
    preventing pre-response leakage into historical as_of queries.
    """
    t_dispatch = datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC)
    t_as_of = datetime(2026, 8, 20, 10, 0, 5, tzinfo=UTC)
    t_response = datetime(2026, 8, 20, 10, 0, 10, tzinfo=UTC)

    current_time = t_dispatch

    def mock_clock() -> datetime:
        return current_time

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal current_time
        # Simulate network roundtrip completing at t_response:
        current_time = t_response
        payload = {
            "query": "late news",
            "results": [
                {
                    "title": "Breaking News",
                    "url": "https://news.com/breaking",
                    "content": "Player injured in late warm-up",
                    "score": 0.9,
                    "published_date": "2026-08-20T09:00:00Z",
                }
            ],
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client, clock=mock_clock)

    try:
        # Request dispatches at t_dispatch (before as_of)
        # Transport completes at t_response (after as_of)
        resp = await provider.search("late news")

        # Must record response completion time, NOT request dispatch time:
        assert resp.retrieved_at == t_response
        assert resp.results[0].retrieved_at == t_response

        # Anti-leakage check: retrieved_at <= t_as_of is FALSE!
        # Result MUST NOT be visible at t_as_of:
        is_visible_at_as_of = resp.results[0].retrieved_at <= t_as_of
        assert is_visible_at_as_of is False

        # But it IS visible after response completion:
        is_visible_after = resp.results[0].retrieved_at <= t_response
        assert is_visible_after is True
    finally:
        await provider.aclose()
