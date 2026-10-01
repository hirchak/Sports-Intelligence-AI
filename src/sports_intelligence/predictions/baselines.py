from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

from sports_intelligence.context.models import MarketPriceItem, MatchContextV1
from sports_intelligence.predictions.contracts import (
    DirectProbabilities,
    Selection,
    probability_table,
)


@dataclass(frozen=True)
class Baseline:
    name: str
    version: str
    probabilities: dict[str, float]
    inputs: dict[str, float]
    limitations: tuple[str, ...]
    unavailable_reason: str | None = None


def poisson_baseline(context: MatchContextV1) -> Baseline:
    """Independent Poisson with observed last-10 attack/defence rate means.

    No home advantage prior, league prior, xG adjustment or ensemble. Use a bounded
    score grid, refuse if its missing tail exceeds 1e-10. No fabricated rate fallback.
    """
    f = context.deterministic_features
    rates = {
        "home_gf": f.home_last10_goals_for_per_match,
        "home_ga": f.home_last10_goals_against_per_match,
        "away_gf": f.away_last10_goals_for_per_match,
        "away_ga": f.away_last10_goals_against_per_match,
    }
    limits = (
        "Unadjusted last-10 rates; no opponent strength or fitted home advantage",
        "Independent goals; small samples and missing scores can bias estimates",
        "Transparent baseline, not calibrated or empirically validated",
    )
    if any(v is None or not math.isfinite(v) or not 0 <= v <= 20 for v in rates.values()):
        return Baseline(
            "statistical", "poisson_v1", {}, {}, limits, "missing_or_invalid_goal_rates"
        )
    inputs = {k: float(v) for k, v in rates.items() if v is not None}
    home_rate = (inputs["home_gf"] + inputs["away_ga"]) / 2
    away_rate = (inputs["away_gf"] + inputs["home_ga"]) / 2
    inputs.update(home_lambda=home_rate, away_lambda=away_rate)
    home_dist, away_dist = _poisson_grid(home_rate), _poisson_grid(away_rate)
    mass = sum(home_dist) * sum(away_dist)
    if abs(1 - mass) > 1e-10:
        return Baseline("statistical", "poisson_v1", {}, inputs, limits, "score_grid_tail_exceeded")
    home = sum(p * q for h, p in enumerate(home_dist) for a, q in enumerate(away_dist) if h > a)
    draw = sum(p * q for p, q in zip(home_dist, away_dist, strict=True))
    away = sum(p * q for h, p in enumerate(home_dist) for a, q in enumerate(away_dist) if h < a)
    total_rate = home_rate + away_rate
    low = _poisson_grid(total_rate)
    over15 = max(0.0, 1 - sum(low[:2]))
    over25 = max(0.0, 1 - sum(low[:3]))
    direct = DirectProbabilities(
        home=home / mass,
        draw=draw / mass,
        away=away / mass,
        over_1_5=over15,
        over_2_5=over25,
        btts_yes=min(over15, (1 - math.exp(-home_rate)) * (1 - math.exp(-away_rate))),
    )
    return Baseline(
        "statistical",
        "poisson_v1",
        {s.value: p for s, p in probability_table(direct).items()},
        inputs,
        limits,
    )


def _poisson_grid(rate: float) -> list[float]:
    result = [math.exp(-rate)]
    for count in range(1, 81):
        result.append(result[-1] * rate / count)
    return result


_MARKET_1X2_ALIASES = frozenset({"h2h_1x2", "h2h", "1x2"})

_PRICE_SELECTIONS = {
    ("h2h_1x2", "home"): Selection.HOME,
    ("h2h_1x2", "draw"): Selection.DRAW,
    ("h2h_1x2", "away"): Selection.AWAY,
    ("h2h", "home"): Selection.HOME,
    ("h2h", "draw"): Selection.DRAW,
    ("h2h", "away"): Selection.AWAY,
    ("1x2", "home"): Selection.HOME,
    ("1x2", "draw"): Selection.DRAW,
    ("1x2", "away"): Selection.AWAY,
    ("ou_15", "over"): Selection.OVER_1_5,
    ("ou_15", "under"): Selection.UNDER_1_5,
    ("ou_25", "over"): Selection.OVER_2_5,
    ("ou_25", "under"): Selection.UNDER_2_5,
    ("btts", "yes"): Selection.BTTS_YES,
    ("btts", "no"): Selection.BTTS_NO,
    ("double_chance", "homeordraw"): Selection.HOME_OR_DRAW,
    ("double_chance", "homeoraway"): Selection.HOME_OR_AWAY,
    ("double_chance", "draworaway"): Selection.DRAW_OR_AWAY,
    ("double_chance", "home_or_draw"): Selection.HOME_OR_DRAW,
    ("double_chance", "home_or_away"): Selection.HOME_OR_AWAY,
    ("double_chance", "draw_or_away"): Selection.DRAW_OR_AWAY,
}


def _canonical_market_name(market: str) -> str:
    """Map the accepted M4 1X2 identifier (and legacy aliases) to one group key."""
    normalized = market.strip().lower()
    return "1x2" if normalized in _MARKET_1X2_ALIASES else normalized


def canonical_selection(price: MarketPriceItem) -> Selection | None:
    market = price.market.strip().lower()
    selection = price.selection.strip().lower()
    if market in _MARKET_1X2_ALIASES:
        market = "h2h_1x2"
    return _PRICE_SELECTIONS.get((market, selection))


def captured_market_probabilities(context: MatchContextV1) -> dict[tuple[str, Selection], float]:
    groups: dict[tuple[str, str], dict[Selection, float]] = {}
    for price in context.market_snapshot.prices:
        selection = canonical_selection(price)
        p = price.no_vig_probability
        if (
            selection is None
            or not price.bookmaker
            or p is None
            or not math.isfinite(p)
            or not 0 <= p <= 1
        ):
            continue
        market = _canonical_market_name(price.market)
        if market == "double_chance":
            # Overlapping DC outcomes do not normalize to sum=1. Do NOT reuse M4's
            # generic mutually-exclusive margin removal for these outcomes.
            continue
        groups.setdefault((price.bookmaker or "", market), {})[selection] = p
    expected = {
        "1x2": {Selection.HOME, Selection.DRAW, Selection.AWAY},
        "ou_15": {Selection.OVER_1_5, Selection.UNDER_1_5},
        "ou_25": {Selection.OVER_2_5, Selection.UNDER_2_5},
        "btts": {Selection.BTTS_YES, Selection.BTTS_NO},
    }
    result: dict[tuple[str, Selection], float] = {}
    for (book, market), values in groups.items():
        if set(values) != expected.get(market) or abs(sum(values.values()) - 1) > 1e-5:
            continue
        result.update({(book, s): p for s, p in values.items()})
        if market == "1x2":
            result.update(
                {
                    (book, Selection.HOME_OR_DRAW): values[Selection.HOME] + values[Selection.DRAW],
                    (book, Selection.HOME_OR_AWAY): values[Selection.HOME] + values[Selection.AWAY],
                    (book, Selection.DRAW_OR_AWAY): values[Selection.DRAW] + values[Selection.AWAY],
                }
            )
    return result


def market_baseline(context: MatchContextV1) -> Baseline:
    captured = captured_market_probabilities(context)
    probabilities = {
        s.value: median(p for (_, selection), p in captured.items() if selection == s)
        for s in Selection
        if any(selection == s for _, selection in captured)
    }
    return Baseline(
        "market",
        "captured_no_vig_v1",
        probabilities,
        {},
        (
            "Captured bookmaker consensus is a benchmark, not ground truth",
            "Double chance derived from same-bookmaker 1X2, not sum-1 overlapping normalization",
            "Medians across books are separate benchmarks; no model averaging",
        ),
        None if probabilities else "no_complete_no_vig_market",
    )
