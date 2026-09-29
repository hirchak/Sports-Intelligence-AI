from __future__ import annotations

import logging
from contextlib import suppress
from datetime import date, datetime
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from sports_intelligence.core.time import utc_now
from sports_intelligence.providers.base import ProviderCapabilities
from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    LineupPublicationState,
    PlayerAvailabilityEntry,
    ProviderAvailabilityResult,
    ProviderCompletedFixture,
    ProviderCompletedFixturesResult,
    ProviderFixture,
    ProviderLeague,
    ProviderLineupPlayer,
    ProviderLineupsResult,
    ProviderResponseMetadata,
    ProviderSeason,
    ProviderStandingRow,
    ProviderStandingsResult,
    ProviderTeam,
    ProviderTeamAvailability,
    ProviderTeamLineup,
    ProviderTeamStatisticsResult,
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

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT_FAMILY = "fixtures_by_date"

# Rate-limit headers relevant for the quota ledger (never include auth
# headers). Values are stored exactly as sent.
_RATE_HEADER_NAMES = (
    "x-ratelimit-requests-limit",
    "x-ratelimit-requests-remaining",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
)


def _rate_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    source = dict(headers)
    lowered = {k.lower(): v for k, v in source.items()}
    return {name: lowered[name] for name in _RATE_HEADER_NAMES if name in lowered}


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
        return ProviderCapabilities(
            provider="api_football",
            supports_fixtures_by_date=True,
            supports_standings=True,
            supports_team_statistics=True,
            supports_availability=True,
            supports_lineups=True,
            supports_completed_fixtures=True,
        )

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
        result.metadata.rate_headers = _rate_headers(response.headers)
        return result

    # ------------------------------------------------------------------
    # M4 category endpoints — real provider data only.
    # ------------------------------------------------------------------

    async def get_standings(
        self, *, provider_league_id: int, season: int | None
    ) -> ProviderStandingsResult:
        params = {"league": str(provider_league_id)}
        if season is not None:
            params["season"] = str(season)
        response = await self._request_with_retry(
            method="GET",
            path="/standings",
            params=params,
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        parsed = parse_standings_response(
            payload,
            provider_league_id=provider_league_id,
            season=season,
            retrieved_at=retrieved_at,
            rate_headers=_rate_headers(response.headers),
        )
        return parsed

    async def get_team_statistics(
        self, *, provider_team_id: int, provider_league_id: int, season: int | None
    ) -> ProviderTeamStatisticsResult:
        params = {
            "team": str(provider_team_id),
            "league": str(provider_league_id),
        }
        if season is not None:
            params["season"] = str(season)
        response = await self._request_with_retry(
            method="GET",
            path="/teams/statistics",
            params=params,
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        return parse_team_statistics_response(
            payload,
            provider_team_id=provider_team_id,
            provider_league_id=provider_league_id,
            season=season,
            retrieved_at=retrieved_at,
            rate_headers=_rate_headers(response.headers),
        )

    async def get_availability(self, *, provider_fixture_id: int) -> ProviderAvailabilityResult:
        response = await self._request_with_retry(
            method="GET",
            path="/injuries",
            params={"fixture": str(provider_fixture_id)},
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        return parse_injuries_response(
            payload,
            provider_fixture_id=provider_fixture_id,
            retrieved_at=retrieved_at,
            rate_headers=_rate_headers(response.headers),
        )

    async def get_lineups(self, *, provider_fixture_id: int) -> ProviderLineupsResult:
        response = await self._request_with_retry(
            method="GET",
            path="/fixtures/lineups",
            params={"fixture": str(provider_fixture_id)},
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        return parse_lineups_response(
            payload,
            provider_fixture_id=provider_fixture_id,
            retrieved_at=retrieved_at,
            rate_headers=_rate_headers(response.headers),
        )

    async def get_completed_fixtures(
        self, *, provider_team_id: int, last_n: int
    ) -> ProviderCompletedFixturesResult:
        response = await self._request_with_retry(
            method="GET",
            path="/fixtures",
            params={
                "team": str(provider_team_id),
                "last": str(min(max(last_n, 1), 20)),
                "status": "ft-aet-pen",
            },
            headers={"x-apisports-key": self._api_key},
        )
        retrieved_at = utc_now()
        payload = self._decode_payload(response)
        return parse_completed_fixtures_response(
            payload,
            provider_team_id=provider_team_id,
            retrieved_at=retrieved_at,
            rate_headers=_rate_headers(response.headers),
        )

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
            raise ProviderAuthError(
                f"api-football auth failed (status {response.status_code})",
                status_code=response.status_code,
                quota_headers=_rate_headers(response.headers),
            )
        if response.status_code == 429:
            raise ProviderRateLimitError(
                "api-football rate limit reached",
                status_code=429,
                quota_headers=_rate_headers(response.headers),
            )
        if response.status_code >= 500:
            raise ProviderServerError(
                f"api-football server error (status {response.status_code})",
                status_code=response.status_code,
                quota_headers=_rate_headers(response.headers),
            )
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


# ---------------------------------------------------------------------------
# M4 category response parsers — pure functions, contract-testable.
# ---------------------------------------------------------------------------


def _response_list(payload: dict[str, object]) -> list[object]:
    raw = payload.get("response")
    if not isinstance(raw, list):
        raise ProviderResponseError("api-football response block is not a list")
    return raw


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def parse_standings_response(
    payload: dict[str, object],
    *,
    provider_league_id: int,
    season: int | None,
    retrieved_at: datetime,
    rate_headers: dict[str, str] | None = None,
) -> ProviderStandingsResult:
    """Parse GET /standings. The `total` standings group is canonical."""
    response_block = _response_list(payload)
    rows: list[ProviderStandingRow] = []
    for league_entry in response_block:
        if not isinstance(league_entry, dict):
            raise ProviderResponseError("standings entry is not an object")
        league_block = league_entry.get("league") or {}
        if not isinstance(league_block, dict):
            continue
        standings_groups = league_block.get("standings")
        if not isinstance(standings_groups, list):
            continue
        for group in standings_groups:
            if not isinstance(group, list):
                continue
            for row in group:
                if not isinstance(row, dict):
                    raise ProviderResponseError("standing row is not an object")
                team = row.get("team") or {}
                if not isinstance(team, dict) or team.get("id") is None:
                    raise ProviderResponseError("standing row missing team id")
                all_block = row.get("all") or {}
                goals = (all_block.get("goals") or {}) if isinstance(all_block, dict) else {}
                rows.append(
                    ProviderStandingRow(
                        rank=_int_or_none(row.get("rank")),
                        provider_team_id=int(team["id"]),
                        team_name=team.get("name"),
                        points=_int_or_none(row.get("points")),
                        played=_int_or_none((all_block or {}).get("played")),
                        wins=_int_or_none((all_block or {}).get("win")),
                        draws=_int_or_none((all_block or {}).get("draw")),
                        losses=_int_or_none((all_block or {}).get("lose")),
                        goals_for=_int_or_none(goals.get("for")),
                        goals_against=_int_or_none(goals.get("against")),
                        form=row.get("form"),
                    )
                )
        # Only the first league entry is relevant for a single-league query.
        break
    return ProviderStandingsResult(
        provider="api_football",
        retrieved_at=retrieved_at,
        rate_headers=rate_headers or {},
        raw_payload=payload,
        provider_league_id=provider_league_id,
        season=season,
        rows=rows,
    )


def parse_team_statistics_response(
    payload: dict[str, object],
    *,
    provider_team_id: int,
    provider_league_id: int,
    season: int | None,
    retrieved_at: datetime,
    rate_headers: dict[str, str] | None = None,
) -> ProviderTeamStatisticsResult:
    """Parse GET /teams/statistics (actual v3 contract, M4.4 §1).

    The v3 `response` block is a SINGLE team-statistics object with:

    - `fixtures.{played,wins,draws,loses}.{home,away,total}` (note
      `loses`, NOT `losses`);
    - `goals.for.total.{home,away,total}` and
      `goals.against.total.{home,away,total}` — the nested `total`
      object holds home/away/total;
    - `clean_sheet.{home,away,total}` and
      `failed_to_score.{home,away,total}`.

    Missing provider values remain None — never fabricated zero.
    """
    raw = payload.get("response")
    if not isinstance(raw, dict):
        raise ProviderResponseError(
            "team statistics response block must be a single object (v3 contract)"
        )
    team = raw.get("team") or {}
    if not isinstance(team, dict) or team.get("id") is None:
        raise ProviderResponseError("team statistics entry missing team id")
    if int(team["id"]) != provider_team_id:
        raise ProviderResponseError(
            f"team statistics returned team {team['id']}, expected {provider_team_id}"
        )
    league = raw.get("league") or {}

    def _split_total(block: object, key: str) -> int | None:
        """Extract the `total` from a `{home, away, total}` split.

        Two shapes occur in the v3 contract:
        - `fixtures.played = {home, away, total}` (key is the metric);
        - `clean_sheet = {home, away, total}` (flat, key == "total").
        """
        if not isinstance(block, dict):
            return None
        if key == "total":
            return _int_or_none(block.get("total"))
        nested = block.get(key)
        if not isinstance(nested, dict):
            return None
        return _int_or_none(nested.get("total"))

    def _goals_total(block: object, side: str) -> int | None:
        """Extract goals.{for,against}.{side}.total where the `side`
        block is `{"total": {"home": .., "away": .., "total": ..}}`."""
        if not isinstance(block, dict):
            return None
        side_block = block.get(side)
        if not isinstance(side_block, dict):
            return None
        total_split = side_block.get("total")
        if not isinstance(total_split, dict):
            return None
        return _int_or_none(total_split.get("total"))

    fixtures = raw.get("fixtures") or {}
    goals = raw.get("goals") or {}
    clean_sheets = raw.get("clean_sheet") or {}
    failed_to_score = raw.get("failed_to_score") or {}
    metrics: dict[str, Any] = {
        "form": raw.get("form"),
        "played": _split_total(fixtures, "played"),
        "wins": _split_total(fixtures, "wins"),
        "draws": _split_total(fixtures, "draws"),
        # API-Football spells the key `loses`; we normalize to `losses`.
        "losses": _split_total(fixtures, "loses"),
        "goals_for": _goals_total(goals, "for"),
        "goals_against": _goals_total(goals, "against"),
        "clean_sheets": _split_total(clean_sheets, "total"),
        "failed_to_score": _split_total(failed_to_score, "total"),
    }
    return ProviderTeamStatisticsResult(
        provider="api_football",
        retrieved_at=retrieved_at,
        rate_headers=rate_headers or {},
        raw_payload=payload,
        provider_team_id=int(team["id"]),
        provider_league_id=(
            int(league.get("id"))  # type: ignore[arg-type]
            if isinstance(league, dict) and league.get("id") is not None
            else provider_league_id
        ),
        season=(
            int(league.get("season"))  # type: ignore[arg-type]
            if isinstance(league, dict) and league.get("season") is not None
            else season
        ),
        metrics=metrics,
    )


def _parse_injury_player(entry: object) -> PlayerAvailabilityEntry:
    if not isinstance(entry, dict):
        raise ProviderResponseError("injury entry is not an object")
    player = entry.get("player") or {}
    if not isinstance(player, dict):
        raise ProviderResponseError("injury player block is not an object")
    entry_type = entry.get("type")
    reason = entry.get("reason")
    # API-Football injury types: "Missing Fixture" (confirmed out) vs
    # "Questionable"/doubtful variants.
    etype = str(entry_type) if entry_type else None
    missing = bool(etype and "missing" in etype.lower())
    return PlayerAvailabilityEntry(
        player_name=player.get("name"),
        provider_player_id=_int_or_none(player.get("id")),
        entry_type=etype,
        reason=str(reason) if reason else None,
        missing=missing,
    )


def parse_injuries_response(
    payload: dict[str, object],
    *,
    provider_fixture_id: int,
    retrieved_at: datetime,
    rate_headers: dict[str, str] | None = None,
) -> ProviderAvailabilityResult:
    """Group one /injuries fixture response into per-team availability."""
    response_block = _response_list(payload)
    by_team: dict[int, ProviderTeamAvailability] = {}
    for entry in response_block:
        if not isinstance(entry, dict):
            raise ProviderResponseError("injuries response entry is not an object")
        team = entry.get("team") or {}
        if not isinstance(team, dict) or team.get("id") is None:
            raise ProviderResponseError("injuries entry missing team id")
        team_id = int(team["id"])
        bucket = by_team.setdefault(
            team_id,
            ProviderTeamAvailability(provider_team_id=team_id, team_name=team.get("name")),
        )
        bucket.entries.append(_parse_injury_player(entry))
    # Empty response → zero confirmed absences is KNOWN_NONE semantics at
    # the collector; the parser reports both teams absent explicitly.
    return ProviderAvailabilityResult(
        provider="api_football",
        retrieved_at=retrieved_at,
        rate_headers=rate_headers or {},
        raw_payload=payload,
        provider_fixture_id=provider_fixture_id,
        teams=sorted(by_team.values(), key=lambda t: t.provider_team_id),
    )


def _parse_lineup_players(block: object, starter: bool) -> list[ProviderLineupPlayer]:
    players: list[ProviderLineupPlayer] = []
    if not isinstance(block, list):
        return players
    for item in block:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or {}
        if not isinstance(player, dict):
            continue
        players.append(
            ProviderLineupPlayer(
                player_name=player.get("name"),
                provider_player_id=_int_or_none(player.get("id")),
                shirt_number=_int_or_none(player.get("number")),
                position=player.get("pos") if isinstance(player.get("pos"), str) else None,
                starter=starter,
            )
        )
    return players


def parse_lineups_response(
    payload: dict[str, object],
    *,
    provider_fixture_id: int,
    retrieved_at: datetime,
    rate_headers: dict[str, str] | None = None,
) -> ProviderLineupsResult:
    """/fixtures/lineups returns data ONLY once a lineup is published
    (confirmed ~20-40 min before kickoff). An empty response means
    NOT_YET_PUBLISHED — never an empty confirmed lineup."""
    response_block = _response_list(payload)
    teams: list[ProviderTeamLineup] = []
    for entry in response_block:
        if not isinstance(entry, dict):
            raise ProviderResponseError("lineups response entry is not an object")
        team = entry.get("team") or {}
        if not isinstance(team, dict) or team.get("id") is None:
            raise ProviderResponseError("lineups entry missing team id")
        formation = entry.get("formation")
        teams.append(
            ProviderTeamLineup(
                provider_team_id=int(team["id"]),
                team_name=team.get("name"),
                formation=formation if isinstance(formation, str) else None,
                # API-Football publishes lineups only when confirmed.
                confirmed=True,
                starters=_parse_lineup_players(entry.get("startXI"), starter=True),
                substitutes=_parse_lineup_players(entry.get("substitutes"), starter=False),
            )
        )
    state = LineupPublicationState.CONFIRMED if teams else LineupPublicationState.NOT_YET_PUBLISHED
    return ProviderLineupsResult(
        provider="api_football",
        retrieved_at=retrieved_at,
        rate_headers=rate_headers or {},
        raw_payload=payload,
        provider_fixture_id=provider_fixture_id,
        publication_state=state,
        teams=teams,
    )


def parse_completed_fixtures_response(
    payload: dict[str, object],
    *,
    provider_team_id: int,
    retrieved_at: datetime,
    rate_headers: dict[str, str] | None = None,
) -> ProviderCompletedFixturesResult:
    response_block = _response_list(payload)
    fixtures: list[ProviderCompletedFixture] = []
    for entry in response_block:
        if not isinstance(entry, dict):
            raise ProviderResponseError("completed fixture entry is not an object")
        fixture_block = entry.get("fixture") or {}
        teams = entry.get("teams") or {}
        score = entry.get("score") or {}
        status = (fixture_block.get("status") or {}) if isinstance(fixture_block, dict) else {}
        status_short = status.get("short")
        if not isinstance(fixture_block, dict) or not fixture_block.get("date"):
            raise ProviderResponseError("completed fixture missing date")
        home = teams.get("home") or {} if isinstance(teams, dict) else {}
        away = teams.get("away") or {} if isinstance(teams, dict) else {}
        fulltime = score.get("fulltime") or {} if isinstance(score, dict) else {}
        kickoff_raw = str(fixture_block["date"]).replace("Z", "+00:00")
        fixtures.append(
            ProviderCompletedFixture(
                provider_fixture_id=int(fixture_block["id"]),
                kickoff_utc=datetime.fromisoformat(kickoff_raw),
                provider_home_team_id=int(home.get("id")),  # type: ignore[arg-type]
                provider_away_team_id=int(away.get("id")),  # type: ignore[arg-type]
                home_goals=_int_or_none(fulltime.get("home")),
                away_goals=_int_or_none(fulltime.get("away")),
                status_short=str(status_short) if status_short else "FT",
            )
        )
    return ProviderCompletedFixturesResult(
        provider="api_football",
        retrieved_at=retrieved_at,
        rate_headers=rate_headers or {},
        raw_payload=payload,
        provider_team_id=provider_team_id,
        fixtures=fixtures,
    )
