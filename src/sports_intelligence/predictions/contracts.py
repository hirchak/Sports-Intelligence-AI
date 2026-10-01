from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
CompactText = Annotated[str, Field(min_length=1, max_length=400)]
SUM_TOLERANCE = 1e-6


class Variant(StrEnum):
    WITH_ODDS = "LLM_WITH_ODDS"
    WITHOUT_ODDS = "LLM_WITHOUT_ODDS"


class Role(StrEnum):
    PRIMARY = "PRIMARY"
    CHALLENGER = "CHALLENGER"


class Selection(StrEnum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    HOME_OR_DRAW = "HOME_OR_DRAW"
    HOME_OR_AWAY = "HOME_OR_AWAY"
    DRAW_OR_AWAY = "DRAW_OR_AWAY"
    OVER_1_5 = "OVER_1_5"
    UNDER_1_5 = "UNDER_1_5"
    OVER_2_5 = "OVER_2_5"
    UNDER_2_5 = "UNDER_2_5"
    BTTS_YES = "BTTS_YES"
    BTTS_NO = "BTTS_NO"


MARKETS = {
    Selection.HOME: "1x2",
    Selection.DRAW: "1x2",
    Selection.AWAY: "1x2",
    Selection.HOME_OR_DRAW: "double_chance",
    Selection.HOME_OR_AWAY: "double_chance",
    Selection.DRAW_OR_AWAY: "double_chance",
    Selection.OVER_1_5: "ou_15",
    Selection.UNDER_1_5: "ou_15",
    Selection.OVER_2_5: "ou_25",
    Selection.UNDER_2_5: "ou_25",
    Selection.BTTS_YES: "btts",
    Selection.BTTS_NO: "btts",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class DirectProbabilities(StrictModel):
    home: Probability
    draw: Probability
    away: Probability
    over_1_5: Probability
    over_2_5: Probability
    btts_yes: Probability

    @model_validator(mode="after")
    def coherence(self) -> DirectProbabilities:
        if abs(self.home + self.draw + self.away - 1) > SUM_TOLERANCE:
            raise ValueError("1X2 sum outside 1e-6 tolerance")
        if self.over_2_5 > self.over_1_5:
            raise ValueError("P(Over 2.5) cannot exceed P(Over 1.5)")
        if self.btts_yes > self.over_1_5:
            raise ValueError("BTTS Yes implies Over 1.5")
        return self


class ConfidenceDiagnostics(StrictModel):
    level: Literal["low", "medium", "high"]
    limitations: Annotated[list[CompactText], Field(max_length=8)]


class EvidenceReference(StrictModel):
    path: Annotated[str, Field(min_length=1, max_length=200)]
    observation: CompactText


class PredictionOutput(StrictModel):
    # All fields required (nullable where appropriate), compatible with native strict JSON schema.
    fixture_id: UUID
    context_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    forecast_phase: Literal["MORNING", "PREMATCH"]
    probabilities: DirectProbabilities | None
    abstain: StrictBool
    abstain_reason: CompactText | None
    confidence: ConfidenceDiagnostics
    evidence_for: Annotated[list[EvidenceReference], Field(max_length=8)]
    evidence_against: Annotated[list[EvidenceReference], Field(max_length=8)]
    risk_flags: Annotated[list[CompactText], Field(max_length=12)]
    summary: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def abstention_consistency(self) -> PredictionOutput:
        if self.abstain:
            if self.probabilities is not None or not self.abstain_reason:
                raise ValueError("abstention requires reason and null probabilities")
        elif self.probabilities is None or self.abstain_reason is not None:
            raise ValueError("forecast requires probabilities and null abstain_reason")
        for refs in (self.evidence_for, self.evidence_against):
            if len({r.path for r in refs}) != len(refs):
                raise ValueError("duplicate evidence paths")
        if {r.path for r in self.evidence_for} & {r.path for r in self.evidence_against}:
            raise ValueError("contradictory evidence paths")
        return self


def probability_table(direct: DirectProbabilities) -> dict[Selection, float]:
    """Explicit tiny 1X2 tolerance normalization; invalid outputs never reach this function."""
    # Revalidate even when caller used model_construct / model_copy(update=...).
    p = DirectProbabilities.model_validate(direct.model_dump())
    total = p.home + p.draw + p.away
    home, draw, away = p.home / total, p.draw / total, p.away / total
    return {
        Selection.HOME: home,
        Selection.DRAW: draw,
        Selection.AWAY: away,
        Selection.HOME_OR_DRAW: home + draw,
        Selection.HOME_OR_AWAY: home + away,
        Selection.DRAW_OR_AWAY: draw + away,
        Selection.OVER_1_5: p.over_1_5,
        Selection.UNDER_1_5: 1 - p.over_1_5,
        Selection.OVER_2_5: p.over_2_5,
        Selection.UNDER_2_5: 1 - p.over_2_5,
        Selection.BTTS_YES: p.btts_yes,
        Selection.BTTS_NO: 1 - p.btts_yes,
    }
