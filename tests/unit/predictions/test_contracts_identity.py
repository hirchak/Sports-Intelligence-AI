from __future__ import annotations

import copy
import uuid

import pytest
from pydantic import ValidationError

from m7_fakes import make_context, valid_output
from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.predictions.contracts import (
    PredictionOutput,
    Selection,
    Variant,
    probability_table,
)
from sports_intelligence.predictions.identity import content_hash, load_prompt, prediction_identity
from sports_intelligence.predictions.projection import project_context
from sports_intelligence.predictions.validator import PredictionValidationError, validate_prediction


@pytest.fixture
def output():
    return valid_output(make_context())


@pytest.mark.parametrize("field", ["home", "draw", "away", "over_1_5", "over_2_5", "btts_yes"])
@pytest.mark.parametrize(
    "invalid", [-0.1, 1.1, float("nan"), float("inf"), float("-inf"), True, "0.5"]
)
def test_probability_invalid_values(output, field, invalid):
    output["probabilities"][field] = invalid
    with pytest.raises(ValidationError):
        PredictionOutput.model_validate(output)


@pytest.mark.parametrize("field", ["home", "draw", "away", "over_1_5", "over_2_5", "btts_yes"])
def test_all_direct_probabilities_required(output, field):
    del output["probabilities"][field]
    with pytest.raises(ValidationError):
        PredictionOutput.model_validate(output)


def test_table_exact_markets_and_derived_probabilities(output):
    direct = PredictionOutput.model_validate(output).probabilities
    table = probability_table(direct)
    assert set(table) == set(Selection) and len(table) == 12
    assert table[Selection.HOME_OR_DRAW] == pytest.approx(0.77)
    assert table[Selection.HOME_OR_AWAY] == pytest.approx(0.73)
    assert table[Selection.DRAW_OR_AWAY] == pytest.approx(0.50)
    for a, b in [
        (Selection.OVER_1_5, Selection.UNDER_1_5),
        (Selection.OVER_2_5, Selection.UNDER_2_5),
        (Selection.BTTS_YES, Selection.BTTS_NO),
    ]:
        assert table[a] + table[b] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"home": 0.7},
        {"over_2_5": 0.8},
        {"btts_yes": 0.8},
        {"unsupported_market": 0.5},
    ],
)
def test_incoherence_rejected(output, change):
    output["probabilities"].update(change)
    with pytest.raises(ValidationError):
        PredictionOutput.model_validate(output)


def test_small_tolerance_only_is_explicit(output):
    output["probabilities"]["home"] += 5e-7
    table = probability_table(PredictionOutput.model_validate(output).probabilities)
    assert sum(table[s] for s in (Selection.HOME, Selection.DRAW, Selection.AWAY)) == pytest.approx(
        1
    )
    output["probabilities"]["home"] += 2e-6
    with pytest.raises(ValidationError):
        PredictionOutput.model_validate(output)


@pytest.mark.parametrize(
    "mutation",
    [
        "fixture",
        "hash",
        "phase",
        "evidence",
        "duplicate",
        "contradictory",
        "extras",
        "quality",
        "text_bound",
    ],
)
def test_validator_rejects_malformed_and_outside_evidence(output, mutation):
    context = make_context()
    payload = project_context(context, Variant.WITH_ODDS)
    can_predict = True
    if mutation == "fixture":
        output["fixture_id"] = str(uuid.uuid4())
    elif mutation == "hash":
        output["context_hash"] = "b" * 64
    elif mutation == "phase":
        output["forecast_phase"] = "PREMATCH"
    elif mutation == "evidence":
        output["evidence_for"][0]["path"] = "future.lineups.confirmed"
    elif mutation == "duplicate":
        output["evidence_for"] *= 2
    elif mutation == "contradictory":
        output["evidence_against"] = copy.deepcopy(output["evidence_for"])
    elif mutation == "extras":
        output["extra"] = 0.5
    elif mutation == "quality":
        can_predict = False
    elif mutation == "text_bound":
        output["summary"] = "x" * 1001
    with pytest.raises(PredictionValidationError):
        validate_prediction(
            output,
            fixture_id=context.fixture_id,
            context_hash="a" * 64,
            phase="MORNING",
            payload=payload,
            can_predict=can_predict,
        )


@pytest.mark.parametrize(
    "probabilities,abstain,reason",
    [
        (None, True, "Insufficient evidence"),
        (None, True, None),
        (None, False, None),
        (
            {
                "home": 0.5,
                "draw": 0.27,
                "away": 0.23,
                "over_1_5": 0.75,
                "over_2_5": 0.54,
                "btts_yes": 0.53,
            },
            True,
            "No data",
        ),
    ],
)
def test_abstention_consistency(output, probabilities, abstain, reason):
    output.update(probabilities=probabilities, abstain=abstain, abstain_reason=reason)
    if probabilities is None and abstain and reason:
        assert PredictionOutput.model_validate(output).abstain
    else:
        with pytest.raises(ValidationError):
            PredictionOutput.model_validate(output)


def test_prompt_hash_stability_and_change():
    prompt = load_prompt()
    assert prompt.hash == load_prompt().hash == content_hash(prompt.content)
    assert prompt.hash != content_hash(prompt.content + "changed")
    assert prompt.version == "1.0.0"


def test_model_config_hash_stable_and_no_secret_fields():
    a = ModelSpec(provider="mock", model="model")
    b = ModelSpec.model_validate(dict(reversed(list(a.model_dump().items()))))
    assert a.hash == b.hash
    assert a.hash != a.model_copy(update={"max_output_tokens": 1600}).hash
    with pytest.raises(ValidationError):
        ModelSpec(provider="mock", model="model", api_key="secret")


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("context_hash", "b" * 64),
        ("prompt_hash", "b" * 64),
        ("prompt_version", "1.1.0"),
        ("provider", "minimax"),
        ("model", "challenger"),
        ("config_hash", "b" * 64),
        ("variant", "LLM_WITHOUT_ODDS"),
        ("role", "CHALLENGER"),
        ("phase", "PREMATCH"),
        ("policy_hash", "b" * 64),
    ],
)
def test_prediction_identity_all_semantics(field, new_value):
    values = dict(
        context_hash="a" * 64,
        prompt_hash="a" * 64,
        prompt_version="1.0.0",
        provider="mock",
        model="model",
        config_hash="a" * 64,
        variant="LLM_WITH_ODDS",
        role="PRIMARY",
        phase="MORNING",
        policy_hash="a" * 64,
    )
    old = prediction_identity(**values)
    assert old == prediction_identity(**values)
    values[field] = new_value
    assert old != prediction_identity(**values)


def test_without_odds_projection_removes_all_known_channels_and_is_pure():
    context = make_context()
    original = context.canonical_json()
    with_odds = project_context(context, Variant.WITH_ODDS)
    without = project_context(context, Variant.WITHOUT_ODDS)
    assert with_odds["market_snapshot"]["prices"]
    assert "market_snapshot" not in without
    assert not any(k.startswith(("market_", "odds_")) for k in without["deterministic_features"])
    assert "source_manifest" not in without["data_quality"]
    assert without["research_claims"]["claims"] == []
    assert not any("odds" in k for k in without["source_manifest"]["sources"])
    without["fixture_identity"]["home_team_name"] = "changed"
    assert context.canonical_json() == original


def test_prompt_filename_requires_semantic_version(tmp_path):
    source = tmp_path / "unversioned.txt"
    source.write_text("Unversioned")
    with pytest.raises(ValueError):
        load_prompt(str(source))


def test_without_odds_removes_nested_provider_market_keys():
    context = make_context()
    data = context.model_dump()
    data["availability"]["home_players"] = [
        {"name": "Player", "odds": 2.1, "metadata": {"market_home_no_vig": 0.5}}
    ]
    projected = project_context(type(context).model_validate(data), Variant.WITHOUT_ODDS)
    assert projected["availability"]["home_players"] == [{"name": "Player", "metadata": {}}]
