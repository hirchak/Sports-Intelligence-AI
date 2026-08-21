from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from sports_intelligence.core.time import utc_now
from sports_intelligence.providers.base import ProviderCapabilities
from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    ProviderFixture,
    ProviderLeague,
    ProviderResponseMetadata,
    ProviderSeason,
    ProviderTeam,
    canonical_request_fingerprint,
)
from sports_intelligence.providers.errors import (
    RETRYABLE_PROVIDER_ERRORS,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)

DEFAULT_BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT_FAMILY = "fixtures_by_date"


class ApiFootballProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
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

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider="api_football", supports_fixtures_by_date=True)

    async def get_fixtures_by_date(
        self, fixture_date: date, timezone_name: str | None = None
    ) -> FixtureDiscoveryResult:
        params = {"date": fixture_date.isoformat()}
        if timezone_name is not None:
            params["timezone"] = timezone_name
        response = await self._request_with_retry(
            method="GET",
            path="/fixtures",
            params=params,
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        result = parse_fixtures_response(
            payload, retrieved_at=retrieved_at, provider="api_football"
        )
        result.metadata.request_fingerprint = canonical_request_fingerprint(
            "api_football", ENDPOINT_FAMILY, params
        )
        rate_limit = response.headers.get("x-ratelimit-requests-remaining")
        if rate_limit is not None:
            with suppress(ValueError):
                result.metadata.rate_limit_remaining = int(rate_limit)
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request_with_retry(
        self, method: str, path: str, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(
                initial=self._backoff_seconds, max=self._backoff_seconds * 4
            ),
            retry=retry_if_exception(lambda exc: isinstance(exc, RETRYABLE_PROVIDER_ERRORS)),
            reraise=True,
        )
        return await retryer(self._single_request, method, path, params, headers)

    async def _single_request(
        self, method: str, path: str, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method, f"{self._base_url}{path}", params=params, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("api-football request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError("api-football transport failure") from exc

        if response.status_code in (401, 403):
            raise ProviderAuthError(f"api-football auth failed (status {response.status_code})")
        if response.status_code == 429:
            raise ProviderRateLimitError("api-football rate limit reached")
        if response.status_code >= 500:
            raise ProviderServerError(f"api-football server error (status {response.status_code})")
        return response

    @staticmethod
    def _decode_payload(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("api-football returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("api-football returned a non-object payload")
        errors = payload.get("errors")
        if errors:
            raise ProviderResponseError(f"api-football reported errors: {errors!r}")
        return payload


def parse_fixtures_response(
    payload: dict[str, object],
    retrieved_at: datetime,
    provider: str,
) -> FixtureDiscoveryResult:
    raw_fixtures = payload.get("response") or []
    if not isinstance(raw_fixtures, list):
        raise ProviderResponseError("api-football response block is not a list")

    leagues: dict[int, ProviderLeague] = {}
    seasons: dict[tuple[int, int], ProviderSeason] = {}
    teams: dict[int, ProviderTeam] = {}
    fixtures: list[ProviderFixture] = []

    for raw in raw_fixtures:
        try:
            if not isinstance(raw, dict):
                raise ProviderResponseError("fixture entry is not an object")
            raw_fixture = raw.get("fixture") or {}
            raw_league = raw.get("league") or {}
            raw_teams = raw.get("teams") or {}
            raw_home = raw_teams.get("home") or {}
            raw_away = raw_teams.get("away") or {}

            league_id = int(raw_league["id"])
            leagues[league_id] = ProviderLeague(
                provider_league_id=league_id,
                name=raw_league.get("name"),
                country=raw_league.get("country"),
            )

            season_value = raw_league.get("season")
            if season_value is not None:
                season = int(season_value)
                seasons[(league_id, season)] = ProviderSeason(
                    provider_league_id=league_id, season=season
                )

            home_id = int(raw_home["id"])
            away_id = int(raw_away["id"])
            teams[home_id] = ProviderTeam(provider_team_id=home_id, name=raw_home.get("name"))
            teams[away_id] = ProviderTeam(provider_team_id=away_id, name=raw_away.get("name"))

            kickoff_raw = raw_fixture.get("date")
            if not kickoff_raw:
                raise ProviderResponseError("fixture entry is missing kickoff date")
            kickoff_utc = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))

            venue_raw = raw_fixture.get("venue") or {}
            status_raw = raw_fixture.get("status") or {}
            status_short = status_raw.get("short")
            if not status_short:
                raise ProviderResponseError("fixture entry is missing status")

            fixtures.append(
                ProviderFixture(
                    provider_fixture_id=int(raw_fixture["id"]),
                    provider_league_id=league_id,
                    provider_season=season_value if season_value is None else int(season_value),
                    provider_home_team_id=home_id,
                    provider_away_team_id=away_id,
                    home_team_name=raw_home.get("name"),
                    away_team_name=raw_away.get("name"),
                    kickoff_utc=kickoff_utc,
                    venue=venue_raw.get("name"),
                    round=raw_league.get("round"),
                    status_short=status_short,
                    status_long=status_raw.get("long"),
                    retrieved_at=retrieved_at,
                    provider=provider,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError("malformed api-football fixture entry") from exc

    return FixtureDiscoveryResult(
        metadata=ProviderResponseMetadata(
            provider=provider,
            endpoint_family=ENDPOINT_FAMILY,
            request_fingerprint=f"{provider}:{ENDPOINT_FAMILY}:unresolved",
            retrieved_at=retrieved_at,
            results_count=len(fixtures),
        ),
        leagues=sorted(leagues.values(), key=lambda league: league.provider_league_id),
        seasons=sorted(
            seasons.values(), key=lambda season: (season.provider_league_id, season.season)
        ),
        teams=sorted(teams.values(), key=lambda team: team.provider_team_id),
        fixtures=fixtures,
        raw_payload=payload,
    )
