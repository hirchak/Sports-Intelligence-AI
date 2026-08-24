from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal


class OddsPriceError(ValueError):
    """Raised when the decimal price or overround is invalid."""


def implied(decimal_price: Decimal) -> Decimal:
    """Decimal-precise 1 / price.

    Raises OddsPriceError for non-positive inputs.
    """
    if decimal_price <= Decimal("0"):
        raise OddsPriceError("decimal price must be positive")
    return Decimal("1") / decimal_price


def overround(implied_probs: Sequence[Decimal]) -> Decimal:
    return sum((p for p in implied_probs), Decimal("0"))


def no_vig(implied_probs: Sequence[Decimal]) -> list[Decimal]:
    """Per-bookmaker no-vig normalization.

    Raises OddsPriceError if the overround is below 1.0 or any input
    is non-positive.
    """
    if not implied_probs:
        raise OddsPriceError("no_vig requires at least one implied probability")
    for p in implied_probs:
        if p <= Decimal("0"):
            raise OddsPriceError("implied probability must be positive")
    total = overround(implied_probs)
    if total < Decimal("1"):
        raise OddsPriceError(f"overround must be >= 1.0 for a valid market (got {total})")
    return [p / total for p in implied_probs]


@dataclass(frozen=True)
class MarketView:
    """Per-bookmaker view of a market: implied + no-vig probabilities."""

    bookmaker: str
    market: str
    selections: tuple[str, ...]
    decimal_prices: tuple[Decimal, ...]
    implied: tuple[Decimal, ...]
    no_vig: tuple[Decimal, ...]
    overround: Decimal

    @property
    def is_complete(self) -> bool:
        """A market view is complete when both sides of the vig are
        normalized (sum of no_vig ≈ 1.0)."""
        if not self.no_vig:
            return False
        total = sum(self.no_vig, Decimal("0"))
        return abs(total - Decimal("1")) < Decimal("0.000001")


def derive_market_view(
    *,
    bookmaker: str,
    market: str,
    selections: Sequence[str],
    decimal_prices: Sequence[Decimal],
) -> MarketView:
    """Implied + no-vig derivation for one bookmaker + market."""
    if len(selections) != len(decimal_prices):
        raise OddsPriceError("selections and prices must have the same length")
    implied: list[Decimal] = []
    for price in decimal_prices:
        if price <= Decimal("1"):
            raise OddsPriceError(f"decimal price must be > 1.0 (got {price})")
        implied.append(Decimal("1") / price)
    try:
        nv = no_vig(implied)
    except OddsPriceError:
        return MarketView(
            bookmaker=bookmaker,
            market=market,
            selections=tuple(selections),
            decimal_prices=tuple(decimal_prices),
            implied=tuple(implied),
            no_vig=(),
            overround=overround(implied),
        )
    return MarketView(
        bookmaker=bookmaker,
        market=market,
        selections=tuple(selections),
        decimal_prices=tuple(decimal_prices),
        implied=tuple(implied),
        no_vig=tuple(nv),
        overround=overround(implied),
    )


def quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
