from __future__ import annotations

from typing import Any

from sports_intelligence.predictions.contracts import PredictionOutput
from sports_intelligence.predictions.projection import valid_evidence_path


class PredictionValidationError(ValueError):
    """Safe, bounded error codes; never echo provider text or context data."""


def validate_prediction(
    raw: dict[str, Any],
    *,
    fixture_id: str,
    context_hash: str,
    phase: str,
    payload: dict[str, Any],
    can_predict: bool,
) -> PredictionOutput:
    try:
        output = PredictionOutput.model_validate(raw)
    except ValueError:
        raise PredictionValidationError("output_schema_invalid") from None
    if (str(output.fixture_id), output.context_hash, output.forecast_phase) != (
        fixture_id,
        context_hash,
        phase,
    ):
        raise PredictionValidationError("output_identity_mismatch")
    if not can_predict and not output.abstain:
        raise PredictionValidationError("quality_prediction_forbidden")
    for ref in output.evidence_for + output.evidence_against:
        if not valid_evidence_path(payload, ref.path):
            raise PredictionValidationError("evidence_outside_supplied_context")
    return output
