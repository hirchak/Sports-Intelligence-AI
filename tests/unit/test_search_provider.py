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
                },
                {
                    "title": "Chelsea Team News",
                    "url": "https://www.chelseafc.com/en/news/article/update",
                    "content": "Reece James is sidelined with a hamstring injury.",
                    "score": 0.82,
                    "published_date": None,
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
