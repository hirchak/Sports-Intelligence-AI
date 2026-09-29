from __future__ import annotations

from decimal import Decimal

import pytest

from sports_intelligence.collectors.odds_math import (
    OddsPriceError,
    derive_market_view,
    implied,
    no_vig,
    overround,
)


def test_implied_basic() -> None:
    assert implied(Decimal("2.00")) == Decimal("0.5")
    assert implied(Decimal("4.00")) == Decimal("0.25")


def test_implied_rejects_non_positive() -> None:
    with pytest.raises(OddsPriceError):
        implied(Decimal("0"))
    with pytest.raises(OddsPriceError):
        implied(Decimal("-1"))


def test_overround_above_one() -> None:
    prices = [Decimal("2.10"), Decimal("3.40"), Decimal("3.60")]
    implied_probs = [Decimal("1") / p for p in prices]
    ov = overround(implied_probs)
    assert ov > Decimal("1.0")
    assert ov == Decimal("1") / Decimal("2.10") + Decimal("1") / Decimal("3.40") + Decimal(
        "1"
    ) / Decimal("3.60")


def test_no_vig_sums_to_one() -> None:
    prices = [Decimal("2.10"), Decimal("3.40"), Decimal("3.60")]
    implied_probs = [Decimal("1") / p for p in prices]
    nv = no_vig(implied_probs)
    total = sum(nv, Decimal("0"))
    assert abs(total - Decimal("1")) < Decimal("0.000001")


def test_no_vig_2_way_sums_to_one() -> None:
    prices = [Decimal("1.85"), Decimal("1.95")]
    implied_probs = [Decimal("1") / p for p in prices]
    nv = no_vig(implied_probs)
    assert abs(sum(nv, Decimal("0")) - Decimal("1")) < Decimal("0.000001")
    assert nv[0] > nv[1]


def test_no_vig_rejects_overround_below_one() -> None:
    with pytest.raises(OddsPriceError):
        no_vig([Decimal("0.5"), Decimal("0.4")])


def test_derive_market_view_rejects_bad_prices() -> None:
    with pytest.raises(OddsPriceError):
        derive_market_view(
            bookmaker="test",
            market="h2h_1x2",
            selections=["home", "draw", "away"],
            decimal_prices=[Decimal("1.0"), Decimal("3.40"), Decimal("3.60")],
        )


def test_derive_market_view_complete() -> None:
    view = derive_market_view(
        bookmaker="test",
        market="h2h_1x2",
        selections=["home", "draw", "away"],
        decimal_prices=[Decimal("2.10"), Decimal("3.40"), Decimal("3.60")],
    )
    assert view.is_complete
    assert len(view.no_vig) == 3
    assert abs(sum(view.no_vig, Decimal("0")) - Decimal("1")) < Decimal("0.000001")


def test_incomplete_market_no_vig_is_not_normalized() -> None:
    """M4.2 §6: no-vig ONLY on a complete expected selection set. An
    incomplete 1X2 (home+away only) must never be normalized even when
    implied probabilities happen to sum above 1."""
    from decimal import Decimal as _D

    from sports_intelligence.collectors.odds_collector import derive_market_view_safe

    # Complete 1X2 → view derived.
    complete = derive_market_view_safe(
        "bookie",
        "h2h_1x2",
        ["home", "draw", "away"],
        (_D("2.10"), _D("3.40"), _D("3.60")),
    )
    assert complete is not None
    assert complete.no_vig

    # Incomplete 1X2 (missing draw) → NO view, no no-vig.
    incomplete = derive_market_view_safe(
        "bookie",
        "h2h_1x2",
        ["home", "away"],
        (_D("1.30"), _D("3.60")),  # implied sum > 1, but incomplete
    )
    assert incomplete is None

    # Incomplete O/U (only over) → no view.
    ou_partial = derive_market_view_safe(
        "bookie",
        "ou_25",
        ["over"],
        (_D("1.85"),),
    )
    assert ou_partial is None

    # Complete BTTS → view.
    btts = derive_market_view_safe(
        "bookie",
        "btts",
        ["yes", "no"],
        (_D("1.75"), _D("2.05")),
    )
    assert btts is not None and btts.no_vig
