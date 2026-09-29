from __future__ import annotations

import asyncio
import re
import urllib.parse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from sports_intelligence.core.logging import get_logger
from sports_intelligence.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from sports_intelligence.providers.search.base import (
    SearchResponse,
    SearchResultItem,
)

logger = get_logger(__name__)

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


def _normalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url.strip())
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        filtered_query = [(k, v) for k, v in query_pairs if k.lower() not in _TRACKING_PARAMS]
        new_query = urllib.parse.urlencode(filtered_query)
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        return urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                new_query,
                "",
            )
        )
    except Exception:
        return url.strip()


_SAFE_HEADER_PREFIXES = ("x-ratelimit-", "retry-after")


def _safe_rate_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in headers.items()
        if any(k.lower().startswith(prefix) for prefix in _SAFE_HEADER_PREFIXES)
    }


def _extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or "unknown"
    except Exception:
        return "unknown"


def _parse_published_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip()
    # Try ISO formats: 2026-09-28T10:15:00Z, 2026-09-28T10:15:00.000Z, etc.
    try:
        # replace Z with +00:00 for fromisoformat compatibility
        iso_str = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass

    # Try RFC 2822 / HTTP format (e.g. "Sat, 22 Aug 2026 00:00:00 GMT" returned by Tavily):
    try:
        dt = parsedate_to_datetime(cleaned)
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass

    # Try YYYY-MM-DD
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=UTC
            )
        except ValueError:
            pass

    return None


class TavilySearchProvider:
    """Production adapter for Tavily Search API.

    API key is passed via constructor and NEVER logged or exposed.
    """

    name: str = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.tavily.com",
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        clock: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Tavily API key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._clock = clock or (lambda: datetime.now(UTC))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> TavilySearchProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> SearchResponse:
        url = f"{self._base_url}/search"
        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "topic": "news",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        # Safe logging without api_key:
        logger.debug(
            "dispatching search query to tavily",
            extra={"provider": self.name, "query_length": len(query), "max_results": max_results},
        )

        retried = 0
        last_exception: Exception | None = None

        while retried <= self._max_retries:
            try:
                response = await self._client.post(url, json=payload)
                # Captured AFTER awaiting the HTTP response, representing observation time:
                retrieved_at = self._clock()
                safe_headers = _safe_rate_headers(response.headers)

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as exc:
                        raise ProviderResponseError("Invalid JSON returned by Tavily") from exc
                    return self._normalize_response(query, data, retrieved_at, safe_headers)

                if response.status_code in (401, 403):
                    raise ProviderAuthError(
                        "Tavily authentication failed: invalid or unauthorized API key",
                        status_code=response.status_code,
                        quota_headers=safe_headers,
                    )

                if response.status_code == 429:
                    raise ProviderRateLimitError(
                        "Tavily rate limit exceeded",
                        status_code=429,
                        quota_headers=safe_headers,
                    )

                if response.status_code >= 500:
                    raise ProviderServerError(
                        f"Tavily server error HTTP {response.status_code}",
                        status_code=response.status_code,
                        quota_headers=safe_headers,
                    )

                raise ProviderResponseError(
                    f"Unexpected HTTP {response.status_code} from Tavily",
                    status_code=response.status_code,
                    quota_headers=safe_headers,
                )

            except (ProviderRateLimitError, ProviderServerError, httpx.TransportError) as exc:
                last_exception = exc
                if isinstance(exc, httpx.TimeoutException):
                    last_exception = ProviderTimeoutError("Tavily request timed out")
                elif isinstance(exc, httpx.TransportError) and not isinstance(
                    exc, (ProviderRateLimitError, ProviderServerError)
                ):
                    last_exception = ProviderTransportError(f"Tavily transport error: {exc}")

                retried += 1
                if retried > self._max_retries:
                    break
                await asyncio.sleep(0.1 * (2 ** (retried - 1)))

        assert last_exception is not None
        raise last_exception

    def _normalize_response(
        self,
        query: str,
        data: dict[str, Any],
        retrieved_at: datetime,
        headers: dict[str, str],
    ) -> SearchResponse:
        results_data = data.get("results")
        if not isinstance(results_data, list):
            results_data = []

        items: list[SearchResultItem] = []
        for raw in results_data:
            if not isinstance(raw, dict):
                continue
            raw_url = str(raw.get("url", "")).strip()
            if not raw_url:
                continue
            url = _normalize_url(raw_url)
            domain = _extract_domain(url)
            title = str(raw.get("title", "")).strip() or "Untitled"
            content = str(raw.get("content", "")).strip()
            score_val = raw.get("score")
            score = float(score_val) if isinstance(score_val, (int, float)) else None
            published_at = _parse_published_at(raw.get("published_date"))

            provider_meta: dict[str, Any] = {"rank": len(items) + 1}
            if raw.get("id"):
                provider_meta["tavily_id"] = str(raw["id"])

            items.append(
                SearchResultItem(
                    url=url,
                    domain=domain,
                    title=title,
                    published_at=published_at,
                    retrieved_at=retrieved_at,
                    content=content,
                    score=score,
                    provider_metadata=provider_meta,
                )
            )

        return SearchResponse(
            query=query,
            results=items,
            retrieved_at=retrieved_at,
            cost_estimate=1,
            raw_payload=data,
            rate_limit_headers=headers,
        )
