import math
import uuid

import pytest
from pydantic import ValidationError

from sports_intelligence.evaluation.config import EvaluationConfig, EvaluationFilters
from sports_intelligence.evaluation.metrics import (
    binary_brier,
    binary_log_loss,
    bucket_index,
    calibration,
    multiclass_brier_sum,
    probability_metrics,
)
from sports_intelligence.evaluation.service import (
    Aggregate,
    aggregate_values,
    keys,
    matches,
    odds_bucket,
)
from sports_intelligence.evaluation.settlement import Outcome


@pytest.mark.parametrize(
    "p,y,brier,loss",
    [
        (0.5, 1, 0.25, math.log(2)),
        (0.75, 1, 0.0625, -math.log(0.75)),
        (0.25, 0, 0.0625, -math.log(0.75)),
        (0.1, 1, 0.81, -math.log(0.1)),
    ],
)
def test_exact_binary(p, y, brier, loss):
    assert binary_brier(p, y) == pytest.approx(brier)
    assert binary_log_loss(p, y) == pytest.approx(loss)


def test_multiclass_convention_sum_not_mean():
    assert multiclass_brier_sum([0.5, 0.3, 0.2], 0) == pytest.approx(0.38)
    assert multiclass_brier_sum([1 / 3] * 3, 1) == pytest.approx(2 / 3)
    assert multiclass_brier_sum([1, 0, 0], 1) == 2


@pytest.mark.parametrize("p,y", [(0, 0), (1, 1), (0, 1), (1, 0)])
def test_extreme_numeric_epsilon(p, y):
    loss = binary_log_loss(p, y, 1e-6)
    assert math.isfinite(loss)
    assert loss == pytest.approx(-math.log(1e-6 if p != y else 1 - 1e-6))
    assert p in (0, 1)  # computation never mutates the stored input


@pytest.mark.parametrize(
    "p,index", [(0, 0), (0.1, 1), (0.599999999, 5), (0.6, 6), (0.9, 9), (1, 9)]
)
def test_decile_boundaries(p, index):
    assert bucket_index(p, EvaluationConfig().calibration_boundaries) == index


def test_weighted_calibration_and_sharpness_known_example():
    config = EvaluationConfig(calibration_boundaries=(0, 0.5, 1))
    samples = [(0.2, 0), (0.4, 1), (0.8, 1)]
    b = calibration(samples, config)
    assert (b[0].sample_size, b[1].sample_size) == (2, 1)
    assert b[0].mean_probability == pytest.approx(0.3)
    assert b[0].event_frequency == 0.5 and b[0].gap == pytest.approx(-0.2)
    metrics = probability_metrics(samples, config)
    assert metrics["calibration_ece"] == pytest.approx(0.2)
    assert metrics["sharpness_mean_squared_distance_from_half"] == pytest.approx(0.19 / 3)
    assert metrics["binary_brier"] == pytest.approx(0.44 / 3)


def test_empty_and_one_item():
    cfg = EvaluationConfig()
    assert all(v is None for v in probability_metrics([], cfg).values())
    assert sum(b.sample_size for b in calibration([], cfg)) == 0
    assert probability_metrics([(0.7, 1)], cfg)["binary_brier"] == pytest.approx(0.09)


def test_coverage_no_bet_abstain_failures_and_roi():
    g = Aggregate({"role": "PRIMARY", "variant": "LLM_WITH_ODDS", "baseline": "llm"})
    ids = [uuid.uuid4() for _ in range(5)]
    g.statuses["SUCCEEDED"].update(ids[:2])  # includes a valid NO_BET
    g.statuses["ABSTAINED"].add(ids[2])
    g.statuses["FAILED"].add(ids[3])
    g.statuses["IN_FLIGHT"].add(ids[4])
    g.displayed_runs.add(ids[0])
    g.candidates = [
        (Outcome.WIN, 2.5, 1.5, 0.2, None),
        (Outcome.LOSS, 2, -1, 0.1, None),
        (Outcome.VOID, 3, 0, 0.3, None),
        (Outcome.PUSH, 2, 0, 0.1, None),
        (Outcome.UNSETTLED, 2.5, None, 0.2, None),
    ]
    v = aggregate_values(g, EvaluationConfig())
    assert v["forecast_coverage"] == (2 / 3, 3)
    assert v["abstention_rate"] == (1 / 3, 3)
    assert v["candidate_display_coverage"] == (0.5, 2)
    assert v["candidate_hit_rate"] == (0.5, 2)
    assert v["research_roi_fixed_unit"] == (0.5 / 3, 3)
    assert v["average_captured_odds"] == (2.4, 5)
    assert v["closing_line_price_proxy"] == (None, 0)


@pytest.mark.parametrize("p", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_bad_probability_rejected(p):
    with pytest.raises(ValueError):
        binary_brier(p, 1)
    with pytest.raises(ValueError):
        binary_log_loss(p, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"epsilon": 0},
        {"epsilon": 1e-300},
        {"epsilon": float("nan")},
        {"calibration_boundaries": (0, 0.5, 0.5, 1)},
        {"calibration_boundaries": (0.1, 1)},
        {"research_stake": 2},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValidationError):
        EvaluationConfig(**kwargs)


def test_segmentation_always_partitions_roles_variants_baselines():
    dims = {
        "role": "PRIMARY",
        "variant": "LLM_WITH_ODDS",
        "baseline": "llm",
        "market": "1x2",
        "confidence": "high",
    }
    assert all(
        k["role"] == "PRIMARY" and k["variant"] == "LLM_WITH_ODDS" and k["baseline"] == "llm"
        for k in keys(dims)
    )
    assert matches(dims, EvaluationFilters(market="1x2", confidence="high"))
    assert not matches(dims, EvaluationFilters(role="CHALLENGER"))
    assert not matches(dims, EvaluationFilters(variant="LLM_WITHOUT_ODDS"))
    assert not matches(dims, EvaluationFilters(baseline="statistical"))
    assert odds_bucket(None, EvaluationConfig()) == "missing"
    assert odds_bucket(2, EvaluationConfig()) == "[2,3)"
