from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from sports_intelligence.providers.errors import (
    RETRYABLE_PROVIDER_ERRORS,
    ProviderAuthError,
    ProviderMappingError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from sports_intelligence.providers.odds.base import OddsProviderResult
from sports_intelligence.providers.odds.mock import EventNotFoundError
from sports_intelligence.providers.odds.parse import parse_event_odds_payload, parse_odds_response

logger = logging.getLogger(__name__)

_ODDS_HEADER_NAMES = ("x-requests-remaining", "x-requests-used", "x-requests-last")

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
    """Live The Odds API v4 client (contract-tested; live not verified).

    Endpoint contract (M4.1 §9):

    - event listing: GET /v4/sports/{sport_key}/events?dateFormat=iso
      (free) used to resolve our fixture → provider event id STRICTLY by
      team names + kickoff tolerance; zero matches and multiple matches
      are hard errors — never guessed;
    - odds: GET /v4/sports/{sport_key}/events/{provider_event_id}/odds;
    - internal fixture UUIDs are NEVER placed into URLs.

    Rate-limit headers (`x-requests-remaining/used/last`) travel with the
    response; `last` is the credit COST of the call and is surfaced via
    `estimate_cost` reconciliation in the quota ledger.
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
        # Always silence httpx logging: even with an injected client the
        # apiKey appears in the URL query string.
        _silence_httpx_info()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def estimate_cost(self, *, markets: Sequence[str], regions: Sequence[str]) -> int:
        """The Odds API credits ≈ regions × markets requested."""
        return max(1, len(set(regions)) * len(set(markets)))

    async def resolve_event(
        self,
        *,
        sport_key: str,
        home_team: str,
        away_team: str,
        commence_time_utc: datetime,
        tolerance_seconds: int = 900,
    ) -> str:
        payload = await self._get_json(f"/sports/{sport_key}/events", params={"dateFormat": "iso"})
        events = payload.get("data") if isinstance(payload.get("data"), list) else None
        if events is None and isinstance(payload, dict):
            # Some responses embed the list directly under different keys.
            for key in ("events",):
                if isinstance(payload.get(key), list):
                    events = payload[key]
                    break
        if not isinstance(events, list):
            raise ProviderResponseError("the-odds-api events payload missing list")
        candidates: list[str] = []
        home_l = home_team.strip().lower()
        away_l = away_team.strip().lower()
        for event in events:
            if not isinstance(event, dict):
                continue
            e_home = str(event.get("home_team", "")).strip().lower()
            e_away = str(event.get("away_team", "")).strip().lower()
            if e_home != home_l or e_away != away_l:
                continue
            commence_raw = event.get("commence_time")
            if not isinstance(commence_raw, str):
                continue
            try:
                e_time = datetime.fromisoformat(commence_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            delta = abs((e_time - commence_time_utc).total_seconds())
            if delta <= tolerance_seconds:
                event_id = event.get("id")
                if isinstance(event_id, str) and event_id:
                    candidates.append(event_id)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) == 0:
            raise ProviderMappingError(
                f"no the-odds-api event for {sport_key} {home_team} vs {away_team}"
            )
        raise ProviderMappingError(
            f"ambiguous the-odds-api event for {sport_key} {home_team} vs {away_team}: "
            f"{len(candidates)} candidates"
        )

    async def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult:
        payload, headers = await self._get_json_with_headers(
            f"/sports/{sport_key}/events/{event_id}/odds",
            params={
                "regions": ",".join(regions),
                "markets": ",".join(markets),
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
        )
        result = parse_event_odds_payload(
            payload,
            provider=self.name,
            rate_headers=headers,
        )
        if result.fixture_id != event_id:
            raise ProviderResponseError("the-odds-api odds payload id mismatch with resolved event")
        return result

    async def fetch_odds(
        self,
        *,
        fixture_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult:
        """Legacy single-event entry kept for direct callers that already
        hold a PROVIDER event id."""
        payload = await self._get_json(
            f"/sports/soccer/events/{fixture_id}/odds",
            params={
                "regions": ",".join(regions),
                "markets": ",".join(markets),
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
        )
        return parse_odds_response(
            payload, fixture_id=fixture_id, markets=list(markets), provider=self.name
        )

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, object]:
        payload, _ = await self._get_json_with_headers(path, params)
        return payload

    async def _get_json_with_headers(
        self, path: str, params: dict[str, str] | None = None
    ) -> tuple[dict[str, object], dict[str, str]]:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(
                initial=self._backoff_seconds, max=self._backoff_seconds * 4
            ),
            retry=retry_if_exception(lambda exc: isinstance(exc, RETRYABLE_PROVIDER_ERRORS)),
            reraise=True,
        )
        response: httpx.Response = await retryer(self._single_get, path, params or {})
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("the-odds-api returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("the-odds-api returned a non-object payload")
        lowered = {k.lower(): v for k, v in response.headers.items()}
        headers = {k: lowered[k] for k in _ODDS_HEADER_NAMES if k in lowered}
        return payload, headers

    async def _single_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        merged = {"apiKey": self._api_key, **params}
        try:
            response = await self._client.get(f"{self._base_url}{path}", params=merged)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("the-odds-api request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError("the-odds-api transport failure") from exc

        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"the-odds-api auth failed (status {response.status_code})",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("the-odds-api rate limit reached", status_code=429)
        if response.status_code == 404:
            raise EventNotFoundError(f"the-odds-api path not found: {path}")
        if response.status_code >= 500:
            raise ProviderServerError(
                f"the-odds-api server error (status {response.status_code})",
                status_code=response.status_code,
            )
        return response


__all__ = [
    "TheOddsApiProvider",
    "EventNotFoundError",
    "build_odds_provider",
]


def build_odds_provider(settings: Any) -> Any:
    from sports_intelligence.providers.errors import ProviderConfigError
    from sports_intelligence.providers.odds.mock import MockOddsProvider

    name = (settings.odds_provider or "").strip().lower()
    if name == "" or name == "mock":
        return MockOddsProvider()
    if name in ("the_odds_api", "theoddsapi"):
        return TheOddsApiProvider(
            api_key=settings.odds_api_key,
            base_url=settings.odds_provider_base_url,
        )
    raise ProviderConfigError(f"unknown ODDS_PROVIDER {name!r}; supported: mock, the_odds_api")
