from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sports_intelligence.providers.odds.base import (
    OddsProviderResult,
    OddsSelectionPrice,
)

# Hand-picked MOCK odds: 1X2, Double Chance, OU 1.5/2.5, BTTS — coherent
# overround ~1.05–1.07, so implied sums slightly above 1.0 and the no-vig
# math exercises real numbers.
_MOCK_BOOKMAKERS: dict[str, dict[str, dict[str, Decimal]]] = {
    "fixture-mock-1": {
        "h2h_1x2": {
            "home": Decimal("2.10"),
            "draw": Decimal("3.40"),
            "away": Decimal("3.60"),
        },
        "double_chance": {
            "home_or_draw": Decimal("1.30"),
            "home_or_away": Decimal("1.25"),
            "draw_or_away": Decimal("1.85"),
        },
        "ou_1_5": {
            "over": Decimal("1.25"),
            "under": Decimal("3.85"),
        },
        "ou_2_5": {
            "over": Decimal("1.85"),
            "under": Decimal("1.95"),
        },
        "btts": {
            "yes": Decimal("1.75"),
            "no": Decimal("2.05"),
        },
    }
}


class MockOddsProvider:
    """Deterministic, keyless MOCK odds provider (CI-safe, no quota)."""

    name = "mock-odds"

    async def fetch_odds(
        self,
        *,
        fixture_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult:
        entries = _MOCK_BOOKMAKERS.get(fixture_id)
        if entries is None:
            return OddsProviderResult(
                provider=self.name,
                fixture_id=fixture_id,
                captured_at=datetime.now(UTC).isoformat(),
                prices=(),
            )
        bookmaker = "mockbookie"
        prices: list[OddsSelectionPrice] = []
        for market in markets:
            market_prices = entries.get(market)
            if market_prices is None:
                continue
            line: Decimal | None = None
            if market in ("ou_1_5", "ou_2_5"):
                line = Decimal("1.5") if market == "ou_1_5" else Decimal("2.5")
            for selection, price in market_prices.items():
                prices.append(
                    OddsSelectionPrice(
                        bookmaker=bookmaker,
                        market=market,
                        selection=selection,
                        line=line,
                        decimal_odds=price,
                    )
                )
        return OddsProviderResult(
            provider=self.name,
            fixture_id=fixture_id,
            captured_at=datetime.now(UTC).isoformat(),
            prices=tuple(prices),
        )

    async def aclose(self) -> None:
        return None
