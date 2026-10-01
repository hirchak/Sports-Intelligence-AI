from __future__ import annotations

from copy import deepcopy
from typing import Any

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.predictions.contracts import Variant


def project_context(context: MatchContextV1, variant: Variant) -> dict[str, Any]:
    """Projection is a copy. Source hashes identify originals but reveal no market prices.

    Odds can also live in provenance, quality diagnostics and free-text research.
    WITHOUT_ODDS removes those unstructured channels conservatively; explicit evidence
    allowlist gives the runtime a useful, auditable view without hidden odds anchors.
    """
    value = deepcopy(context.model_dump(mode="json"))
    if variant == Variant.WITH_ODDS:
        return value
    value.pop("market_snapshot")
    for key in list(value["deterministic_features"]):
        if key.startswith(("market_", "odds_")) or key == "missing_features":
            del value["deterministic_features"][key]
    # Original quality remains in DB; masked view exposes only its numeric/eligibility facts.
    quality = value["data_quality"]
    value["data_quality"] = {
        k: quality[k]
        for k in (
            "schema_version",
            "forecast_phase",
            "as_of",
            "overall_score",
            "quality_band",
            "can_predict",
        )
    }
    # Claims are arbitrary text, potentially containing prices even if classified team_news.
    value["research_claims"] = {"status": "MASKED_FOR_WITHOUT_ODDS", "claims": []}
    value["source_manifest"] = {
        "source_fingerprint": context.source_manifest.source_fingerprint,
        "sources": {
            k: {
                field: entry.model_dump(mode="json")[field]
                for field in (
                    "category",
                    "table",
                    "snapshot_id",
                    "provider",
                    "captured_at",
                    "payload_id",
                )
            }
            for k, entry in context.source_manifest.sources.items()
            if "odds" not in k.lower() and "market" not in k.lower() and "research" not in k.lower()
        },
    }
    masked = _remove_market_keys(value)
    assert isinstance(masked, dict)
    return masked


def _remove_market_keys(value: Any) -> Any:
    """Defensive masking of market keys in provider-owned nested dicts (players/form)."""
    if isinstance(value, dict):
        return {
            key: _remove_market_keys(child)
            for key, child in value.items()
            if not key.lower().startswith(("market_", "odds_", "bookmaker", "no_vig"))
            and key.lower() not in ("odds", "decimal_odds", "implied_probability", "captured_odds")
        }
    if isinstance(value, list):
        return [_remove_market_keys(child) for child in value]
    return value


def valid_evidence_path(payload: dict[str, Any], path: str) -> bool:
    if not path or len(path.split(".")) > 12:
        return False
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return current is not None and current != [] and current != {}
