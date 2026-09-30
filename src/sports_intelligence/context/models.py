from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MatchContextV1:
    """Immutable, typed MatchContext V1 data structure.

    Sections strictly ordered 1 through 13 per specification.
    Contains ONLY point-in-time facts available at or before `as_of`.
    Zero future leakage, zero prediction probabilities, zero LLM text.
    """

    # Identity
    schema_version: str
    fixture_id: str
    forecast_phase: str
    as_of: str

    # Sections 1–13
    fixture_identity: dict[str, Any]
    team_form: dict[str, Any]
    home_away_context: dict[str, Any]
    season_strength: dict[str, Any]
    schedule_fatigue: dict[str, Any]
    availability: dict[str, Any]
    lineups: dict[str, Any]
    head_to_head: dict[str, Any]
    research_claims: dict[str, Any]
    market_snapshot: dict[str, Any]
    deterministic_features: dict[str, Any]
    data_quality: dict[str, Any]
    source_manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        """Deterministic canonical JSON serialization for stable cryptographic hashing."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
