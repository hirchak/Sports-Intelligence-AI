"""Explicitly synthetic M7 fixtures; never evidence of forecasting accuracy."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from sports_intelligence.context.builder import assemble_match_context_v1
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.features.builder import build_features
from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.providers.llm.base import LLMError, LLMResult
from sports_intelligence.quality.engine import evaluate_data_quality

FIXTURE_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")


def make_context() -> MatchContextV1:
    as_of = datetime(2026, 8, 21, 10, tzinfo=UTC)
    fixture = SelectedFixtureInfo(
        fixture_id=FIXTURE_ID,
        league_id=uuid.uuid4(),
        season_id=None,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=as_of + timedelta(hours=6),
        venue=None,
        round=None,
        status="NS",
        league_slug="synthetic-m7",
        league_name="Synthetic",
        home_team_name="Home",
        away_team_name="Away",
        home_provider_mappings=[],
        away_provider_mappings=[],
    )
    evidence = SelectedEvidence(
        fixture_id=FIXTURE_ID,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fixture,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )
    manifest = build_source_manifest(evidence)
    features = build_features(evidence)
    quality = evaluate_data_quality(evidence, features, manifest)
    data = assemble_match_context_v1(evidence, features, quality, manifest).model_dump()
    data["data_quality"].update(can_predict=True, overall_score=0.9, critical_missing=[])
    data["deterministic_features"].update(
        home_last10_goals_for_per_match=1.8,
        home_last10_goals_against_per_match=0.8,
        away_last10_goals_for_per_match=1.2,
        away_last10_goals_against_per_match=1.4,
    )
    data["market_snapshot"].update(
        has_odds=True,
        captured_at=as_of.isoformat(),
        prices=[
            {
                "market": "h2h_1x2",
                "selection": s,
                "decimal_odds": odds,
                "implied_probability": 1 / odds,
                "no_vig_probability": nv,
                "bookmaker": "synthetic",
            }
            for s, odds, nv in (("home", 2.0, 0.46), ("draw", 3.3, 0.28), ("away", 3.5, 0.26))
        ]
        + [
            {
                "market": "double_chance",
                "selection": selection,
                "decimal_odds": odds,
                "implied_probability": 1 / odds,
                # M4 stores no-vig DC for presentation, but its generic normalization
                # treats overlapping selections as mutually exclusive. M7 must ignore
                # these values and derive its benchmark from same-bookmaker h2h_1x2.
                "no_vig_probability": direct_no_vig,
                "bookmaker": "synthetic",
            }
            for selection, odds, direct_no_vig in (
                ("home_or_draw", 1.30, 0.3656),
                ("home_or_away", 1.25, 0.3800),
                ("draw_or_away", 1.85, 0.2544),
            )
        ]
        + [
            {
                "market": "ou_15",
                "selection": s,
                "decimal_odds": odds,
                "implied_probability": 1 / odds,
                "no_vig_probability": nv,
                "bookmaker": "synthetic",
                "line": 1.5,
            }
            for s, odds, nv in (("over", 1.5, 0.64), ("under", 2.7, 0.36))
        ],
    )
    return MatchContextV1.model_validate(data)


def valid_output(context: MatchContextV1, context_hash: str = "a" * 64) -> dict[str, Any]:
    return {
        "fixture_id": context.fixture_id,
        "forecast_phase": context.forecast_phase,
        "context_hash": context_hash,
        "probabilities": {
            "home": 0.5,
            "draw": 0.27,
            "away": 0.23,
            "over_1_5": 0.75,
            "over_2_5": 0.54,
            "btts_yes": 0.53,
        },
        "abstain": False,
        "abstain_reason": None,
        "confidence": {"level": "low", "limitations": ["Synthetic"]},
        "evidence_for": [{"path": "data_quality.overall_score", "observation": "Synthetic"}],
        "evidence_against": [],
        "risk_flags": ["synthetic"],
        "summary": "Synthetic forecast",
    }


class ScriptedProvider:
    def __init__(
        self,
        responses: list[dict[str, Any] | LLMError],
        provider: str = "mock",
        actual_model: str | None = None,
    ) -> None:
        self.responses = deepcopy(responses)
        self.provider = provider
        self.actual_model = actual_model
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def generate_structured(
        self, *, config: ModelSpec, payload: dict[str, Any], **kwargs: Any
    ) -> LLMResult:
        self.calls.append(deepcopy(payload))
        item = self.responses.pop(0)
        if isinstance(item, LLMError):
            raise item
        return LLMResult(
            item,
            self.provider,
            self.actual_model or config.model,
            request_id="synthetic-request",
            input_tokens=10,
            output_tokens=20,
            finish_reason="stop",
        )

    async def aclose(self) -> None:
        self.closed = True
