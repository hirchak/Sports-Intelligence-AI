from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from sports_intelligence.evaluation.config import EvaluationConfig
from sports_intelligence.predictions.config import ModelSpec, PredictionPolicy
from sports_intelligence.predictions.contracts import StrictModel, Variant
from sports_intelligence.predictions.identity import fingerprint

Text = Annotated[str, Field(min_length=1, max_length=2000)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
Phase = Literal["MORNING", "PREMATCH"]


class ExperimentStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED_FOR_EXPERIMENT = "APPROVED_FOR_EXPERIMENT"
    EXPERIMENT_RUNNING = "EXPERIMENT_RUNNING"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"


EXPERIMENT_TRANSITIONS = {
    "DRAFT": {"READY", "CANCELLED"},
    "READY": {"QUEUED", "CANCELLED"},
    "QUEUED": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "INSUFFICIENT_DATA", "CANCELLED"},
    "FAILED": {"QUEUED"},
}
PROPOSAL_TRANSITIONS = {
    "PROPOSED": {"APPROVED_FOR_EXPERIMENT", "REJECTED"},
    "APPROVED_FOR_EXPERIMENT": {"EXPERIMENT_RUNNING", "REJECTED"},
    "EXPERIMENT_RUNNING": {"REJECTED", "PROMOTED"},
    "PROMOTED": {"ROLLED_BACK"},
}


def transition(current: str, target: str, *, proposal: bool = False) -> None:
    allowed = PROPOSAL_TRANSITIONS if proposal else EXPERIMENT_TRANSITIONS
    if target not in allowed.get(current, set()):
        raise ValueError("invalid_state_transition")


class ArmRequest(StrictModel):
    source: Literal["replay", "historical_primary", "historical_challenger"] = "replay"
    route: ShortText = "prediction_primary"
    prompt: Literal["default", "candidate"] = "default"
    variant: Variant = Variant.WITH_ODDS
    phase: Phase = "MORNING"


class Population(StrictModel):
    start: datetime
    end: datetime
    fixture_ids: Annotated[tuple[UUID, ...], Field(max_length=1000)] = ()
    context_ids: Annotated[tuple[UUID, ...], Field(max_length=1000)] = ()
    league_ids: Annotated[tuple[UUID, ...], Field(max_length=100)] = ()
    markets: tuple[Literal["1x2", "double_chance", "ou_15", "ou_25", "btts"], ...] = (
        "1x2",
        "double_chance",
        "ou_15",
        "ou_25",
        "btts",
    )

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("aware_time_required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid(self) -> Population:
        if self.start >= self.end or (self.end - self.start).days > 366:
            raise ValueError("invalid_bounded_period")
        if not self.markets or len(set(self.markets)) != len(self.markets):
            raise ValueError("invalid_market_scope")
        if len(set(self.context_ids)) != len(self.context_ids):
            raise ValueError("duplicate_context_scope")
        if len(set(self.fixture_ids)) != len(self.fixture_ids):
            raise ValueError("duplicate_fixture_scope")
        return self


class ExperimentDefinition(StrictModel):
    name: ShortText
    hypothesis: Text
    control: ArmRequest = Field(default_factory=ArmRequest)
    treatment: ArmRequest = Field(default_factory=lambda: ArmRequest(route="prediction_challenger"))
    population: Population
    created_by: ShortText = "local"
    max_fixtures: Annotated[int, Field(ge=1, le=1000)] = 50
    max_llm_calls: Annotated[int, Field(ge=0, le=10000)] = 100
    max_calls_per_arm: Annotated[int, Field(ge=0, le=5000)] = 50
    batch_size: Annotated[int, Field(ge=1, le=20)] = 5
    min_paired_fixtures: Annotated[int, Field(ge=1, le=10000)] = 100
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


class FrozenArm(StrictModel):
    request: ArmRequest
    models: tuple[ModelSpec, ...]
    fallback_errors: tuple[str, ...]
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    prompt_content: str
    prompt_source: str
    policy: PredictionPolicy
    route_hash: str

    @property
    def hash(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class ProposalExperimentError(ValueError):
    """Safe refusal codes for proposal-to-experiment mapping."""


def validate_proposal_experiment(component: str, arms: dict[str, FrozenArm]) -> None:
    if component not in ("prompt", "model"):
        raise ProposalExperimentError("unsupported_proposal_experiment_component")
    if set(arms) != {"control", "treatment"}:
        raise ProposalExperimentError("incompatible_proposal_experiment_definition")
    control, treatment = arms["control"], arms["treatment"]
    if (
        control.request.source != "replay"
        or treatment.request.source != "replay"
        or control.request.phase != treatment.request.phase
        or control.request.variant != treatment.request.variant
        or control.policy.hash != treatment.policy.hash
    ):
        raise ProposalExperimentError("incompatible_proposal_experiment_definition")
    if component == "prompt":
        valid = control.prompt_hash != treatment.prompt_hash and control.models == treatment.models
    else:
        valid = (
            control.prompt_hash == treatment.prompt_hash
            and control.models[0].hash != treatment.models[0].hash
        )
    if not valid:
        raise ProposalExperimentError("incompatible_proposal_experiment_definition")


class RunRequest(StrictModel):
    rerun_key: UUID | None = None
    live_opt_in: bool = False


class HumanAction(StrictModel):
    actor: ShortText
    reason: Text


class RecordedDecision(HumanAction):
    status: Literal["PROMOTED", "ROLLED_BACK"]


class ApproveRequest(HumanAction):
    experiment: ExperimentDefinition | None = None


class AnalystOutput(StrictModel):
    title: ShortText
    problem: Text
    hypothesis: Text
    proposed_change: Text
    expected_effect: Text
    test_plan: Text
    risks: Text
    risk_level: Literal["low", "medium", "high"]
    affected_component: Literal["prompt", "model", "data_quality", "features", "ranking", "sources"]

    @model_validator(mode="after")
    def qualitative_only(self) -> AnalystOutput:
        # Known football labels carry digits, but are not measured values.
        # Remove only complete labels before applying the existing strict numeric-claim guard.
        for value in self.model_dump().values():
            prose = re.sub(
                r"(?<!\w)(?:H2H|1X2|O/U\s*(?:1\.5|2\.5))(?!\w)", "", str(value), flags=re.IGNORECASE
            )
            if any(c.isdigit() for c in prose) or "%" in prose:
                raise ValueError("analyst_numeric_claim_forbidden")
        return self
