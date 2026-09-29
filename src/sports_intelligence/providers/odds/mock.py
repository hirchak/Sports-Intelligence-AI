from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sports_intelligence.providers.odds.base import (
    OddsProviderResult,
    OddsSelectionPrice,
)

# Hand-picked MOCK odds: 1X2, Double Chance, OU 1.5/2.5, BTTS — coherent
# overround ~1.05–1.07 so implied sums slightly above 1.0 and the no-vig
# math exercises real numbers. Allowed ONLY under the mock provider.
_MOCK_EVENT_ID = "mock-event-0001"
_MOCK_HOME = "Mock United"
_MOCK_AWAY = "Mock City"
_MARKETS: dict[str, dict[str, Decimal]] = {
    "h2h": {"home": Decimal("2.10"), "draw": Decimal("3.40"), "away": Decimal("3.60")},
    "double_chance": {
        "HomeOrDraw": Decimal("1.30"),
        "HomeOrAway": Decimal("1.25"),
        "DrawOrAway": Decimal("1.85"),
    },
    "totals": {
        "Over": Decimal("1.85"),
        "Under": Decimal("1.95"),
    },
    "btts": {"Yes": Decimal("1.75"), "No": Decimal("2.05")},
}


class EventNotFoundError(LookupError):
    pass


class MockOddsProvider:
    """Deterministic, keyless MOCK odds provider (CI-safe, no quota).

    Implements the same strict event-resolution contract as the live
    adapter: only the canned fixture resolves; anything else raises.
    """

    name = "mock-odds"

    def __init__(
        self,
        *,
        sport_key: str = "soccer_mock",
        home_team: str = _MOCK_HOME,
        away_team: str = _MOCK_AWAY,
        commence_time_utc: datetime | None = None,
        ambiguous_events: int = 1,
    ) -> None:
        self._sport_key = sport_key
        self._home = home_team
        self._away = away_team
        self._commence = commence_time_utc or datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
        self._ambiguous = ambiguous_events

    async def resolve_event(
        self,
        *,
        sport_key: str,
        home_team: str,
        away_team: str,
        commence_time_utc: datetime,
        tolerance_seconds: int = 900,
    ) -> str:
        if sport_key != self._sport_key:
            raise EventNotFoundError(f"unknown mock sport_key {sport_key!r}")
        if (
            home_team.strip().lower() != self._home.lower()
            or away_team.strip().lower() != self._away.lower()
        ):
            raise EventNotFoundError("no mock event matches teams")
        if abs((commence_time_utc - self._commence).total_seconds()) > tolerance_seconds:
            raise EventNotFoundError("no mock event within kickoff tolerance")
        if self._ambiguous > 1:
            raise RuntimeError("ambiguous mock event")
        return _MOCK_EVENT_ID

    def estimate_cost(self, *, markets: Sequence[str], regions: Sequence[str]) -> int:
        # The Odds API credits ≈ regions × markets; mirror that in MOCK.
        return max(1, len(set(regions)) * len(set(markets)))

    def request_markets(self, markets: Sequence[str]) -> Sequence[str]:
        keys = list(markets)
        if "totals" in keys and "alternate_totals" not in keys:
            keys.append("alternate_totals")
        return keys

    async def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult:
        if event_id != _MOCK_EVENT_ID:
            return OddsProviderResult(
                provider=self.name,
                fixture_id=event_id,
                captured_at=datetime.now(UTC).isoformat(),
                prices=(),
                raw_payload={"bookmakers": []},
            )
        bookmaker = "mockbookie"
        prices: list[OddsSelectionPrice] = []
        for market in markets:
            outcomes = _MARKETS.get(market)
            if outcomes is None:
                continue
            line: Decimal | None = None
            canonical_market = market
            if market == "totals":
                # Emit both OU lines from one totals outcome set.
                for selection, price in outcomes.items():
                    for line_value in (Decimal("1.5"), Decimal("2.5")):
                        prices.append(
                            OddsSelectionPrice(
                                bookmaker=bookmaker,
                                market=f"ou_{str(line_value).replace('.', '')}",
                                selection=selection.lower(),
                                line=line_value,
                                decimal_odds=price,
                            )
                        )
                continue
            for selection, price in outcomes.items():
                prices.append(
                    OddsSelectionPrice(
                        bookmaker=bookmaker,
                        market=canonical_market,
                        selection=_selection_key(market, selection),
                        line=line,
                        decimal_odds=price,
                    )
                )
        return OddsProviderResult(
            provider=self.name,
            fixture_id=event_id,
            captured_at=datetime.now(UTC).isoformat(),
            prices=tuple(prices),
            raw_payload={
                "id": event_id,
                "sport_key": sport_key,
                "home_team": self._home,
                "away_team": self._away,
                "bookmakers": [{"key": bookmaker, "markets": []}],
            },
        )

    async def aclose(self) -> None:
        return None


def _selection_key(market: str, provider_selection: str) -> str:
    lowered = provider_selection.lower().replace(" ", "_")
    if market == "h2h":
        return lowered  # home / draw / away already canonical
    return lowered
