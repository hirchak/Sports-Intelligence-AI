"""The Odds API v4 response normalization (no business logic in JSON).

Maps provider payloads to the provider-independent `OddsProviderResult`
contract. Pure functions — deterministic and contract-testable without
any network access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sports_intelligence.providers.errors import ProviderResponseError
from sports_intelligence.providers.odds.base import (
    OddsProviderResult,
    OddsSelectionPrice,
)

_PROVIDER_TO_CANONICAL: Mapping[str, str] = {
    "h2h": "h2h_1x2",
    "double_chance": "double_chance",
    "btts": "btts",
}

_SELECTIONS_DOUBLE_CHANCE: Mapping[str, str] = {
    "home_or_draw": "home_or_draw",
    "homeordraw": "home_or_draw",
    "home_or_away": "home_or_away",
    "homeoraway": "home_or_away",
    "draw_or_away": "draw_or_away",
    "draworaway": "draw_or_away",
}

_SELECTIONS_BTTS_YES = frozenset({"yes", "both_teams_to_score"})
_SELECTIONS_BTTS_NO = frozenset({"no", "either_team_to_score"})


def _as_decimal(value: object, *, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - any parse failure means malformed payload
        raise ProviderResponseError(f"invalid {label} {value!r}") from exc


def _str(name: object, *, label: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ProviderResponseError(f"{label} is missing a non-empty name")
    return name.strip()


def _canonical_1x2(name: str, home_team: object, away_team: object) -> str:
    lowered = name.lower()
    if lowered == "draw":
        return "draw"
    if isinstance(home_team, str) and name.lower() == home_team.lower():
        return "home"
    if isinstance(away_team, str) and name.lower() == away_team.lower():
        return "away"
    raise ProviderResponseError(f"unrecognized 1X2 outcome {name!r}")


def _canonical_double_chance(name: str) -> str:
    key = name.lower().replace(" ", "_")
    if key not in _SELECTIONS_DOUBLE_CHANCE:
        raise ProviderResponseError(f"unrecognized double-chance outcome {name!r}")
    return _SELECTIONS_DOUBLE_CHANCE[key]


def _canonical_btts(name: str) -> str:
    lowered = name.lower()
    if lowered in _SELECTIONS_BTTS_YES:
        return "yes"
    if lowered in _SELECTIONS_BTTS_NO:
        return "no"
    raise ProviderResponseError(f"unrecognized btts outcome {name!r}")


def _canonical_totals(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("over"):
        return "over"
    if lowered.startswith("under"):
        return "under"
    raise ProviderResponseError(f"unrecognized totals outcome {name!r}")


def _canonical_selection(market: str, name: str, home_team: object, away_team: object) -> str:
    if market == "h2h_1x2":
        return _canonical_1x2(name, home_team, away_team)
    if market == "double_chance":
        return _canonical_double_chance(name)
    if market == "btts":
        return _canonical_btts(name)
    if market.startswith("ou_"):
        return _canonical_totals(name)
    raise ProviderResponseError(f"unknown canonical market {market!r}")


def _decimal_to_label(value: Decimal) -> str:
    # Canonical market labels drop the decimal: 1.5 -> "15", 2.5 -> "25".
    if value == int(value):
        return str(int(value))
    return str((value * 10).to_integral_value())


def _total_market_for(point: object, totals_markers: Sequence[Decimal]) -> str | None:
    try:
        line_d = _as_decimal(point, label="totals point")
    except ProviderResponseError:
        return None
    if line_d not in set(totals_markers):
        return None
    return f"ou_{_decimal_to_label(line_d)}"


def _line_for_market(market: str, point: object) -> Decimal | None:
    if not market.startswith("ou_"):
        return None
    try:
        return _as_decimal(point, label="totals point")
    except ProviderResponseError:
        return None


def _parse_last_update(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return datetime.now(UTC).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def parse_odds_response(
    payload: Mapping[str, object],
    *,
    fixture_id: str,
    markets: Sequence[str],
    provider: str,
    totals_markers: Sequence[Decimal] = (
        Decimal("1.5"),
        Decimal("2.5"),
    ),
) -> OddsProviderResult:
    """Parse a single-event The Odds API v4 response into
    `OddsProviderResult`.

    Whitelisted provider markets (`markets` parameter) are kept; unknown
    markets are skipped silently. Whitelisted markets that are
    malformed raise `ProviderResponseError`.
    """
    bookmakers_raw = payload.get("bookmakers")
    if not isinstance(bookmakers_raw, list):
        raise ProviderResponseError("odds payload is missing the bookmakers list")

    captured_at = _parse_last_update(payload.get("last_update"))
    whitelist = set(markets)
    prices: list[OddsSelectionPrice] = []
    home_team = payload.get("home_team")
    away_team = payload.get("away_team")
    seen: set[tuple[str, str, str, str]] = set()

    for bookmaker_raw in bookmakers_raw:
        if not isinstance(bookmaker_raw, Mapping):
            raise ProviderResponseError("bookmaker entry is not an object")
        bookmaker_key = bookmaker_raw.get("key") or bookmaker_raw.get("title")
        bookmaker = _str(bookmaker_key, label="bookmaker")
        markets_raw = bookmaker_raw.get("markets")
        if not isinstance(markets_raw, list):
            continue

        for market_raw in markets_raw:
            if not isinstance(market_raw, Mapping):
                continue
            provider_key = market_raw.get("key")
            if not isinstance(provider_key, str):
                continue

            if provider_key not in whitelist and provider_key != "totals":
                continue

            outcomes_raw = market_raw.get("outcomes")
            if not isinstance(outcomes_raw, list):
                continue

            for outcome_raw in outcomes_raw:
                if not isinstance(outcome_raw, Mapping):
                    continue
                canonical = _canonical_for_outcome(
                    provider_key=provider_key,
                    outcome_raw=outcome_raw,
                    totals_markers=totals_markers,
                    whitelist=whitelist,
                )
                if canonical is None:
                    continue
                name = _str(outcome_raw.get("name"), label="outcome")
                try:
                    selection = _canonical_selection(canonical, name, home_team, away_team)
                except ProviderResponseError:
                    continue
                decimal_odds = _as_decimal(outcome_raw.get("price"), label="decimal odds")
                line = _line_for_market(canonical, outcome_raw.get("point"))
                dedupe_key = (
                    bookmaker,
                    canonical,
                    selection,
                    str(line) if line is not None else "",
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                prices.append(
                    OddsSelectionPrice(
                        bookmaker=bookmaker,
                        market=canonical,
                        selection=selection,
                        line=line,
                        decimal_odds=decimal_odds,
                    )
                )

    return OddsProviderResult(
        provider=provider,
        fixture_id=fixture_id,
        captured_at=captured_at,
        prices=tuple(prices),
        raw_payload_ref=_raw_ref(payload),
    )


def _canonical_for_outcome(
    *,
    provider_key: str,
    outcome_raw: Mapping[str, object],
    totals_markers: Sequence[Decimal],
    whitelist: set[str],
) -> str | None:
    if provider_key in _PROVIDER_TO_CANONICAL:
        return _PROVIDER_TO_CANONICAL[provider_key]
    if provider_key == "totals" and "totals" in whitelist:
        return _total_market_for(outcome_raw.get("point"), totals_markers)
    return None


def _raw_ref(payload: Mapping[str, object]) -> str | None:
    event_id = payload.get("id")
    return event_id if isinstance(event_id, str) else None
