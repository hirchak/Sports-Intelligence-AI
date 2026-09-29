from __future__ import annotations

from datetime import UTC, datetime

from sports_intelligence.providers.search.base import SearchResultItem
from sports_intelligence.research.dedup import (
    content_sha256,
    deduplicate_search_results,
    normalize_url,
)


def test_normalize_url_strips_tracking_params() -> None:
    url = "https://www.bbc.com/sport/football/12345?utm_source=twitter&utm_medium=social&fbclid=abc"
    normalized = normalize_url(url)
    assert "utm_source" not in normalized
    assert "utm_medium" not in normalized
    assert "fbclid" not in normalized
    assert normalized == "https://www.bbc.com/sport/football/12345"


def test_normalize_url_lowercases_host_and_strips_slash() -> None:
    url = "HTTP://WWW.Skysports.COM/football/news/"
    normalized = normalize_url(url)
    assert normalized == "http://www.skysports.com/football/news"


def test_content_sha256_deterministic() -> None:
    h1 = content_sha256("Some sports snippet")
    h2 = content_sha256("Some sports snippet")
    h3 = content_sha256("Different text")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_deduplicate_search_results_by_url_and_content() -> None:
    now = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    item1 = SearchResultItem(
        url="https://site.com/news?utm_source=feed",
        title="Title 1",
        snippet="Same snippet content",
        published_at=now,
        domain="site.com",
        relevance_score=0.8,
    )
    # Same canonical URL, different tracking
    item2 = SearchResultItem(
        url="https://site.com/news?utm_campaign=daily",
        title="Title 1 Duplicate",
        snippet="Different snippet",
        published_at=now,
        domain="site.com",
        relevance_score=0.9,
    )
    # Different URL, identical snippet content
    item3 = SearchResultItem(
        url="https://other.com/news",
        title="Syndicated article",
        snippet="Same snippet content",
        published_at=now,
        domain="other.com",
        relevance_score=0.7,
    )
    # Completely unique
    item4 = SearchResultItem(
        url="https://unique.com/article",
        title="Unique article",
        snippet="Unique news story content",
        published_at=now,
        domain="unique.com",
        relevance_score=0.85,
    )

    deduped = deduplicate_search_results([item1, item2, item3, item4])
    # item2 is duplicate URL of item1; item3 has identical content hash to item1
    # Only item1 and item4 should remain
    assert len(deduped) == 2
    urls = [d.url for d in deduped]
    assert "https://unique.com/article" in urls
