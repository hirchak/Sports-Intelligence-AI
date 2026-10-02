"""Narrow football-token exception; numeric measurements remain forbidden."""

import pytest
from pydantic import ValidationError

from sports_intelligence.experiments.contracts import AnalystOutput


def qualitative(**overrides):
    data = {
        "title": "Synthetic hypothesis",
        "problem": "Synthetic evidence only.",
        "hypothesis": "Measure before changing.",
        "proposed_change": "Test a registered candidate.",
        "expected_effect": "Uncertain improvement.",
        "test_plan": "Paired frozen replay.",
        "risks": "Small sample.",
        "risk_level": "low",
        "affected_component": "prompt",
    }
    return {**data, **overrides}


@pytest.mark.parametrize("label", ["H2H", "1X2", "O/U 1.5", "O/U 2.5", "h2h", "O/U2.5"])
def test_football_identifiers_are_qualitative_labels(label):
    result = AnalystOutput.model_validate(
        qualitative(
            title="Inspect " + label,
            problem="Investigate " + label,
            test_plan="Compare " + label + " on frozen inputs.",
        )
    )
    assert label in result.title


@pytest.mark.parametrize(
    "claim",
    [
        "H2H sample 138",
        "1X2 Brier 0.12",
        "O/U 1.5 ROI 20%",
        "O/U 2.5 log loss 0.4",
        "1X2 cost $1.50",
        "O/U 1.500",
        "H2H999",
        "1X20",
        "O/U 2.5e3",
    ],
)
def test_domain_label_does_not_hide_hallucinated_measurement(claim):
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(qualitative(problem=claim))


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_size", 138),
        ("metrics", {"brier": 0.12}),
        ("status", "PROMOTED"),
        ("evidence_references", ["invented"]),
    ],
)
def test_domain_exception_keeps_strict_factual_schema(field, value):
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(qualitative(title="Inspect H2H", **{field: value}))


async def test_missing_backend_approval_advice_fails_closed():
    import httpx

    from sports_intelligence.bot.backend_client import BackendClient, BackendPayloadError

    payload = {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "Synthetic",
        "status": "PROPOSED",
        "problem": "Synthetic",
        "hypothesis": "Synthetic",
        "test_plan": "Synthetic",
        "sample_size": 0,
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(BackendPayloadError, match="approval advice"):
            await BackendClient("https://synthetic.invalid", client=http).improvement_view(
                payload["id"]
            )
