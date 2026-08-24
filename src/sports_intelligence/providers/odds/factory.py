from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import (
    RETRYABLE_PROVIDER_ERRORS,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from sports_intelligence.providers.odds.base import OddsProvider, OddsProviderResult
from sports_intelligence.providers.odds.mock import MockOddsProvider
from sports_intelligence.providers.odds.parse import parse_odds_response

_SILENCED_HTTPX_LOGGERS: set[str] = set()


def _silence_httpx_info() -> None:
    """Suppress httpx INFO request/response logs that include the full
    URL — the Odds API carries `apiKey` in the query string, so a default
    httpx logger would leak the secret to any log sink."""
    for name in ("httpx", "httpx._client", "httpcore", "httpcore.http11"):
        if name in _SILENCED_HTTPX_LOGGERS:
            continue
        logging.getLogger(name).setLevel(logging.WARNING)
        _SILENCED_HTTPX_LOGGERS.add(name)


class TheOddsApiProvider:
    """Live Odds API client (v4). Architecture ready for future swap.

    Response payload is normalized through `parse.parse_odds_response`
    so callers consume a provider-independent contract (contract-tested,
    live not verified in M4).
    """

    name = "theoddsapi"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        # Always silence the httpx logger: even when the caller injects
        # their own client, the apiKey appears in the URL, so any log
        # emitted by httpx would leak the secret.
        _silence_httpx_info()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_odds(
        self,
        *,
        fixture_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(
                initial=self._backoff_seconds, max=self._backoff_seconds * 4
            ),
            retry=retry_if_exception(lambda exc: isinstance(exc, RETRYABLE_PROVIDER_ERRORS)),
            reraise=True,
        )
        response: httpx.Response = await retryer(self._single_request, fixture_id, markets, regions)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("the-odds-api returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("the-odds-api returned a non-object payload")

        try:
            return parse_odds_response(
                payload,
                fixture_id=fixture_id,
                markets=list(markets),
                provider=self.name,
            )
        except ProviderResponseError:
            raise
        except Exception as exc:  # defensive — provider parse is total
            raise ProviderResponseError(
                f"the-odds-api payload normalization failed: {exc!r}"
            ) from exc

    async def _single_request(
        self,
        fixture_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> httpx.Response:
        try:
            response = await self._client.get(
                f"{self._base_url}/sports/soccer/events/{fixture_id}/odds",
                params={
                    "apiKey": self._api_key,
                    "regions": ",".join(regions),
                    "markets": ",".join(markets),
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                },
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("the-odds-api request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError("the-odds-api transport failure") from exc

        if response.status_code in (401, 403):
            raise ProviderAuthError(f"the-odds-api auth failed (status {response.status_code})")
        if response.status_code == 429:
            raise ProviderRateLimitError("the-odds-api rate limit reached")
        if response.status_code >= 500:
            raise ProviderServerError(f"the-odds-api server error (status {response.status_code})")
        return response


def build_odds_provider(settings: Settings) -> OddsProvider:
    """Wire the configured odds provider (MOCK or live)."""
    name = (settings.odds_provider or "").strip().lower()
    if name == "" or name == "mock":
        return MockOddsProvider()
    if name == "the_odds_api" or name == "theoddsapi":
        return TheOddsApiProvider(
            api_key=settings.odds_api_key,
            base_url=settings.odds_provider_base_url,
        )
    # Unknown provider — fail loud at startup.
    from sports_intelligence.providers.errors import ProviderConfigError

    raise ProviderConfigError(f"unknown ODDS_PROVIDER {name!r}; supported: mock, the_odds_api")
