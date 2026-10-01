from __future__ import annotations

import math

import pytest

from m7_fakes import make_context, valid_output
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.predictions.baselines import market_baseline, poisson_baseline
from sports_intelligence.predictions.config import RankingPolicy
from sports_intelligence.predictions.contracts import PredictionOutput, Selection, probability_table
from sports_intelligence.ranking.engine import rank_candidates


def table(context):
    return probability_table(PredictionOutput.model_validate(valid_output(context)).probabilities)


def test_poisson_is_deterministic_all_markets_no_ensemble():
    context = make_context()
    a, b = poisson_baseline(context), poisson_baseline(context)
    assert a == b and set(a.probabilities) == set(Selection)
    assert a.inputs["home_lambda"] == pytest.approx(1.6)
    assert a.inputs["away_lambda"] == pytest.approx(1.0)
    assert a.probabilities[Selection.BTTS_YES] == pytest.approx(
        (1 - math.exp(-1.6)) * (1 - math.exp(-1))
    )
    data = context.model_dump()
    data["market_snapshot"]["prices"] = []
    assert poisson_baseline(MatchContextV1.model_validate(data)) == a
    assert sum(
        a.probabilities[s] for s in (Selection.HOME, Selection.DRAW, Selection.AWAY)
    ) == pytest.approx(1)


def test_missing_baseline_is_unavailable_never_fake_input():
    context = make_context()
    data = context.model_dump()
    data["deterministic_features"]["home_last10_goals_for_per_match"] = None
    baseline = poisson_baseline(MatchContextV1.model_validate(data))
    assert baseline.probabilities == {} and baseline.unavailable_reason


def test_zero_rates_are_known_zero():
    data = make_context().model_dump()
    for key in [
        "home_last10_goals_for_per_match",
        "home_last10_goals_against_per_match",
        "away_last10_goals_for_per_match",
        "away_last10_goals_against_per_match",
    ]:
        data["deterministic_features"][key] = 0.0
    b = poisson_baseline(MatchContextV1.model_validate(data))
    assert b.probabilities[Selection.DRAW] == 1 and b.probabilities[Selection.OVER_1_5] == 0


def test_market_baseline_derived_double_chance_not_ground_truth():
    context = make_context()
    baseline = market_baseline(context)
    assert baseline.probabilities[Selection.HOME] == 0.46
    assert baseline.probabilities[Selection.HOME_OR_DRAW] == pytest.approx(0.74)
    assert "not ground truth" in baseline.limitations[0]


def test_candidate_edge_ev_math():
    context = make_context()
    candidates = rank_candidates(
        context, table(context), RankingPolicy(min_model_probability=0, min_edge=-1)
    )
    home = next(c for c in candidates if c.selection == Selection.HOME)
    assert home.edge == pytest.approx(0.5 - 0.46)
    assert home.expected_value == pytest.approx(0.5 * 2 - 1)
    assert len(candidates) == 12


@pytest.mark.parametrize(
    "policy,reason",
    [
        ({"min_decimal_odds": 2.01}, "odds_below_minimum"),
        ({"max_decimal_odds": 1.99}, "odds_above_maximum"),
        ({"min_model_probability": 0.50001}, "probability_below_minimum"),
        ({"min_edge": 0.04001}, "edge_below_minimum"),
        ({"min_data_quality": 0.91}, "data_quality_below_threshold"),
        ({"allowed_markets": ("btts",)}, "market_not_allowed"),
        ({"league_allow": ("other",)}, "league_not_allowed"),
        ({"league_deny": ("synthetic-m7",)}, "league_not_allowed"),
    ],
)
def test_policy_boundaries_reject(policy, reason):
    context = make_context()
    candidate = next(
        c
        for c in rank_candidates(context, table(context), RankingPolicy(**policy))
        if c.selection == Selection.HOME
    )
    assert reason in candidate.filter_reasons and not candidate.displayed


def test_threshold_equality_included():
    context = make_context()
    p = RankingPolicy(
        min_decimal_odds=2,
        max_decimal_odds=2,
        min_model_probability=0.5,
        min_edge=0.5 - 0.46,
        min_data_quality=0.9,
    )
    home = next(
        c for c in rank_candidates(context, table(context), p) if c.selection == Selection.HOME
    )
    assert home.displayed and home.filter_reasons == ()


@pytest.mark.parametrize(
    "kind", ["stale", "future", "missing_odds", "missing_nv", "incomplete_market"]
)
def test_stale_missing_future_odds(kind):
    data = make_context().model_dump()
    if kind == "stale":
        data["market_snapshot"]["captured_at"] = "2026-08-21T07:59:59+00:00"
    elif kind == "future":
        data["market_snapshot"]["captured_at"] = "2026-08-21T10:00:01+00:00"
    elif kind == "missing_odds":
        data["market_snapshot"]["prices"] = []
    elif kind == "missing_nv":
        data["market_snapshot"]["prices"][0]["no_vig_probability"] = None
    elif kind == "incomplete_market":
        data["market_snapshot"]["prices"] = data["market_snapshot"]["prices"][:1]
    context = MatchContextV1.model_validate(data)
    home = next(
        c
        for c in rank_candidates(
            context, table(context), RankingPolicy(min_model_probability=0, min_edge=-1)
        )
        if c.selection == Selection.HOME
    )
    assert not home.displayed
    assert any(
        r in home.filter_reasons
        for r in ("stale_or_future_odds", "missing_odds", "missing_market_probability")
    )


def test_zero_candidate_and_stable_order_maximum():
    context = make_context()
    probabilities = table(context)
    assert not any(
        c.displayed for c in rank_candidates(context, probabilities, RankingPolicy(min_edge=1))
    )
    policy = RankingPolicy(min_model_probability=0, min_edge=-1, max_candidates=1)
    a, b = (
        rank_candidates(context, probabilities, policy),
        rank_candidates(context, probabilities, policy),
    )
    assert a == b and sum(c.displayed for c in a) == 1
    assert any("maximum_candidates_exceeded" in c.filter_reasons for c in a)


def test_context_quality_stale_odds_excluded_even_with_long_ranking_ttl():
    data = make_context().model_dump()
    data["data_quality"]["stale_sources"] = ["odds"]
    context = MatchContextV1.model_validate(data)
    candidates = rank_candidates(
        context,
        table(context),
        RankingPolicy(min_model_probability=0, min_edge=-1, max_odds_age_seconds=86400),
    )
    assert not any(c.displayed for c in candidates)
    assert all("stale_or_future_odds" in c.filter_reasons for c in candidates)


def test_decimal_edge_threshold_equality_ignores_only_float_drift():
    data = make_context().model_dump()
    data["market_snapshot"]["prices"][0]["no_vig_probability"] = 0.55
    data["market_snapshot"]["prices"][1]["no_vig_probability"] = 0.25
    data["market_snapshot"]["prices"][2]["no_vig_probability"] = 0.20
    context = MatchContextV1.model_validate(data)
    direct = PredictionOutput.model_validate(valid_output(context)).probabilities.model_dump()
    direct.update(home=0.6, draw=0.2, away=0.2)
    from sports_intelligence.predictions.contracts import DirectProbabilities

    probabilities = probability_table(DirectProbabilities.model_validate(direct))
    policy = RankingPolicy(min_model_probability=0, min_edge=0.05)
    home = next(
        c for c in rank_candidates(context, probabilities, policy) if c.selection == Selection.HOME
    )
    assert home.displayed and home.edge == pytest.approx(0.05)
    strict = policy.model_copy(update={"min_edge": 0.0500001})
    home = next(
        c for c in rank_candidates(context, probabilities, strict) if c.selection == Selection.HOME
    )
    assert not home.displayed
