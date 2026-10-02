from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.providers.llm.base import LLMResult


class MockLLMProvider:
    """Synthetic deterministic plumbing fixture; probabilities are NOT market evidence."""

    async def generate_structured(
        self,
        *,
        task_type: str,
        config: ModelSpec,
        system_prompt: str,
        payload: dict[str, Any],
        output_schema: type[BaseModel],
        request_id: str,
    ) -> LLMResult:
        if task_type == "improvement_analysis":
            return LLMResult(
                parsed_output={
                    "title": "Inspect missing evidence before changing the predictor",
                    "problem": "Synthetic comparison is measurement infrastructure only.",
                    "hypothesis": "Better evidence completeness may reduce uncertainty.",
                    "proposed_change": "Test a versioned candidate prompt emphasizing missingness.",
                    "expected_effect": "Potentially better abstention; requires measurement.",
                    "test_plan": "Run paired replay; inspect held-out cases.",
                    "risks": "Small samples and correlated markets may mislead interpretation.",
                    "risk_level": "low",
                    "affected_component": "prompt",
                },
                provider="mock",
                model=config.model,
                request_id=request_id,
                latency_ms=0,
                finish_reason="stop",
            )
        context = payload["context"]
        return LLMResult(
            parsed_output={
                "fixture_id": context["fixture_id"],
                "context_hash": payload["context_hash"],
                "forecast_phase": context["forecast_phase"],
                "probabilities": {
                    "home": 0.50,
                    "draw": 0.27,
                    "away": 0.23,
                    "over_1_5": 0.75,
                    "over_2_5": 0.54,
                    "btts_yes": 0.53,
                },
                "abstain": False,
                "abstain_reason": None,
                "confidence": {"level": "low", "limitations": ["Синтетический MOCK прогноз"]},
                "evidence_for": [
                    {
                        "path": "data_quality.overall_score",
                        "observation": "MOCK проверяет только переданные метаданные качества",
                    }
                ],
                "evidence_against": [],
                "risk_flags": ["synthetic_mock"],
                "summary": "Синтетический прогноз только для локальной проверки без ключей.",
            },
            provider="mock",
            model=config.model,
            request_id=request_id,
            latency_ms=0,
            finish_reason="stop",
        )

    async def aclose(self) -> None:
        pass
