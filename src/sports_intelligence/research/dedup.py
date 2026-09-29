from __future__ import annotations

import hashlib
import urllib.parse

from sports_intelligence.providers.search.base import SearchResultItem

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to prevent duplicate storage across generated queries."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        filtered_query = [(k, v) for k, v in query_pairs if k.lower() not in _TRACKING_PARAMS]
        new_query = urllib.parse.urlencode(filtered_query)

        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        normalized = urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",  # params
                new_query,
                "",  # fragment stripped
            )
        )
        return normalized
    except Exception:
        return url.strip()


def content_sha256(text: str) -> str:
    """Compute deterministic SHA256 hex digest of source text."""
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deduplicate_search_results(results: list[SearchResultItem]) -> list[SearchResultItem]:
    """Deduplicate candidate documents within a research run.

    Deduplication rules:
    - deduplicates by normalized URL;
    - deduplicates by content hash;
    - preserves the result with highest relevance score or earlier occurrence;
    - never removes distinct articles from the same domain.
    """
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    unique_items: list[SearchResultItem] = []

    for item in results:
        norm_url = normalize_url(item.url)
        c_hash = content_sha256(item.content or item.title)

        if norm_url in seen_urls:
            continue
        if c_hash in seen_hashes:
            continue

        seen_urls.add(norm_url)
        seen_hashes.add(c_hash)
        unique_items.append(item)

    return unique_items
