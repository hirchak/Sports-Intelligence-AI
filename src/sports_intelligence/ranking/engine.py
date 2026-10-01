from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.predictions.baselines import (
    canonical_selection,
    captured_market_probabilities,
)
from sports_intelligence.predictions.config import RankingPolicy
from sports_intelligence.predictions.contracts import MARKETS, Selection


@dataclass(frozen=True)
class Candidate:
    selection: Selection
    market: str
    model_probability: float
    captured_odds: float | None
    market_probability: float | None
    bookmaker: str | None
    edge: float | None
    expected_value: float | None
    filter_reasons: tuple[str, ...]
    rank: int | None = None
    displayed: bool = False


def rank_candidates(
    context: MatchContextV1,
    probabilities: dict[Selection, float],
    policy: RankingPolicy,
) -> list[Candidate]:
    if set(probabilities) != set(Selection) or any(
        not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()
    ):
        raise ValueError("ranking requires complete finite probability table")
    no_vig = captured_market_probabilities(context)
    captured = context.market_snapshot.captured_at
    stale = True
    if captured:
        as_of = datetime.fromisoformat(context.as_of)
        timestamp = datetime.fromisoformat(captured)
        age = (as_of - timestamp).total_seconds()
        stale = age < 0 or age > policy.max_odds_age_seconds
    if "odds" in context.data_quality.stale_sources:
        stale = True
    league = context.fixture_identity.league_slug
    league_id = context.fixture_identity.league_id
    candidates: list[Candidate] = []
    for selection in Selection:
        prices = [p for p in context.market_snapshot.prices if canonical_selection(p) == selection]
        prices = [p for p in prices if math.isfinite(p.decimal_odds) and p.decimal_odds > 1]
        # Prefer highest captured price WITH a valid matching benchmark, then stable bookmaker.
        prices.sort(
            key=lambda p: (
                (p.bookmaker or "", selection) not in no_vig,
                -p.decimal_odds,
                p.bookmaker or "",
            )
        )
        price = prices[0] if prices else None
        odds = price.decimal_odds if price else None
        market_p = no_vig.get((price.bookmaker or "", selection)) if price else None
        probability = probabilities[selection]
        edge = probability - market_p if market_p is not None else None
        ev = probability * odds - 1 if odds is not None else None
        reasons: list[str] = []
        if MARKETS[selection] not in policy.allowed_markets:
            reasons.append("market_not_allowed")
        if (
            not context.data_quality.can_predict
            or context.data_quality.overall_score < policy.min_data_quality
        ):
            reasons.append("data_quality_below_threshold")
        if (league in policy.league_deny or league_id in policy.league_deny) or (
            policy.league_allow
            and league not in policy.league_allow
            and league_id not in policy.league_allow
        ):
            reasons.append("league_not_allowed")
        if odds is None:
            reasons.append("missing_odds")
        elif odds < policy.min_decimal_odds:
            reasons.append("odds_below_minimum")
        elif policy.max_decimal_odds is not None and odds > policy.max_decimal_odds:
            reasons.append("odds_above_maximum")
        if stale:
            reasons.append("stale_or_future_odds")
        if probability < policy.min_model_probability - policy.comparison_tolerance:
            reasons.append("probability_below_minimum")
        if market_p is None:
            reasons.append("missing_market_probability")
        elif edge is not None and edge < policy.min_edge - policy.comparison_tolerance:
            reasons.append("edge_below_minimum")
        candidates.append(
            Candidate(
                selection,
                MARKETS[selection],
                probability,
                odds,
                market_p,
                price.bookmaker if price else None,
                edge,
                ev,
                tuple(reasons),
            )
        )
    passed = sorted(
        (c for c in candidates if not c.filter_reasons),
        key=lambda c: (
            -(c.edge or 0),
            -(c.expected_value or 0),
            -c.model_probability,
            c.selection.value,
        ),
    )
    ranks = {c.selection: i + 1 for i, c in enumerate(passed)}
    return [
        replace(
            c,
            rank=ranks.get(c.selection),
            displayed=c.selection in ranks and ranks[c.selection] <= policy.max_candidates,
            filter_reasons=c.filter_reasons
            or (
                ("maximum_candidates_exceeded",)
                if c.selection in ranks and ranks[c.selection] > policy.max_candidates
                else ()
            ),
        )
        for c in candidates
    ]
