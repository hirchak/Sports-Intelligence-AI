from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC
from typing import Any

from sports_intelligence.context.provenance import SourceManifest
from sports_intelligence.context.selector import SelectedEvidence
from sports_intelligence.core.phases import ForecastPhase, ResearchState
from sports_intelligence.features.builder import DeterministicFeatures


@dataclass(frozen=True)
class QualityWeights:
    fixture_identity: float = 0.15
    form: float = 0.20
    season_stats: float = 0.15
    availability: float = 0.15
    odds: float = 0.15
    research: float = 0.10
    lineups: float = 0.10


@dataclass(frozen=True)
class QualityReportData:
    schema_version: str
    forecast_phase: str
    as_of: str
    overall_score: float
    quality_band: str
    can_predict: bool
    dimension_scores: dict[str, float]
    critical_missing: list[str]
    missing_fields: list[dict[str, Any]]
    warnings: list[str]
    conflicts: list[dict[str, Any]]
    provider_errors: list[dict[str, Any]]
    stale_sources: list[str]
    source_manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_data_quality(
    evidence: SelectedEvidence,
    features: DeterministicFeatures,
    manifest: SourceManifest,
    *,
    weights: QualityWeights | None = None,
    min_predict_score: float = 0.65,
) -> QualityReportData:
    """Deterministic Data Quality Engine evaluating evidence completeness, freshness, and conflicts.

    Rules:
    - Pure calculation, zero external API calls.
    - MORNING phase excludes Lineups dimension from score denominator (Lineups = N/A).
    - PREMATCH phase evaluates confirmed/unconfirmed publication state.
    - Missingness is explicit with reasons (unknown != healthy;
      provider error != no useful results).
    - Configurable dimension weights and prediction threshold.
    """
    w = weights or QualityWeights()
    scores: dict[str, float] = {}
    active_weights: dict[str, float] = {}
    critical_missing: list[str] = []
    missing_fields: list[dict[str, Any]] = []
    warnings: list[str] = []
    conflicts: list[dict[str, Any]] = []
    provider_errors: list[dict[str, Any]] = []
    stale_sources: list[str] = []

    # 1. Fixture Identity
    fix = evidence.fixture
    if fix.kickoff_at is None or fix.home_team_id is None or fix.away_team_id is None:
        scores["fixture_identity"] = 0.0
        critical_missing.append("fixture_core_identity")
        missing_fields.append(
            {
                "field": "fixture_identity",
                "reason": "Missing core IDs or kickoff",
            }
        )
    elif fix.season_id is None:
        scores["fixture_identity"] = 0.70
        warnings.append("Fixture season_id is missing; season stats unavailable")
    else:
        scores["fixture_identity"] = 1.0
    active_weights["fixture_identity"] = w.fixture_identity

    # 2. Form
    has_home_form = evidence.home_form is not None
    has_away_form = evidence.away_form is not None
    if has_home_form and has_away_form:
        h_sz = features.home_sample_size or 0
        a_sz = features.away_sample_size or 0
        if h_sz >= 10 and a_sz >= 10:
            scores["form"] = 1.0
        elif h_sz >= 5 and a_sz >= 5:
            scores["form"] = 0.90
        else:
            scores["form"] = 0.75
            warnings.append(f"Small form sample size: home={h_sz}, away={a_sz}")
    elif has_home_form or has_away_form:
        scores["form"] = 0.45
        missing_team = "away" if has_home_form else "home"
        missing_fields.append(
            {
                "field": "form",
                "reason": f"Form snapshot missing for {missing_team} team",
            }
        )
        warnings.append(f"Form snapshot missing for {missing_team} team")
    else:
        scores["form"] = 0.0
        missing_fields.append(
            {
                "field": "form",
                "reason": "No form snapshots available for either team",
            }
        )
        warnings.append("No form snapshots available for either team")
    active_weights["form"] = w.form

    # 3. Season Stats
    if evidence.standings is not None:
        if features.home_league_position is not None and features.away_league_position is not None:
            scores["season_stats"] = 1.0
        else:
            scores["season_stats"] = 0.75
            warnings.append("Standings found but missing one or both team ranks")
    elif evidence.home_team_stats is not None or evidence.away_team_stats is not None:
        scores["season_stats"] = 0.60
    else:
        scores["season_stats"] = 0.0
        missing_fields.append(
            {
                "field": "season_stats",
                "reason": "No standings or team statistics <= as_of",
            }
        )
    active_weights["season_stats"] = w.season_stats

    # 4. Availability
    h_state = features.home_availability_state or "UNKNOWN"
    a_state = features.away_availability_state or "UNKNOWN"
    if h_state in ("KNOWN_PRESENT", "KNOWN_NONE") and a_state in ("KNOWN_PRESENT", "KNOWN_NONE"):
        scores["availability"] = 1.0
    elif h_state in ("KNOWN_PRESENT", "KNOWN_NONE") or a_state in ("KNOWN_PRESENT", "KNOWN_NONE"):
        scores["availability"] = 0.70
        warnings.append(f"Partial availability certainty: home={h_state}, away={a_state}")
    elif h_state == "UNKNOWN" and a_state == "UNKNOWN":
        scores["availability"] = 0.40
        warnings.append("Availability state is UNKNOWN for both teams")
    else:
        scores["availability"] = 0.20
    active_weights["availability"] = w.availability

    # Availability conflicts
    if (features.home_availability_conflict_count or 0) > 0:
        conflicts.append(
            {
                "source": "home_availability",
                "count": features.home_availability_conflict_count,
            }
        )
    if (features.away_availability_conflict_count or 0) > 0:
        conflicts.append(
            {
                "source": "away_availability",
                "count": features.away_availability_conflict_count,
            }
        )

    # 5. Odds
    if evidence.odds_set is not None:
        if (
            features.market_home_no_vig is not None
            and features.market_draw_no_vig is not None
            and features.market_away_no_vig is not None
        ):
            if (
                features.market_over25_no_vig is not None
                and features.market_btts_yes_no_vig is not None
            ):
                scores["odds"] = 1.0
            else:
                scores["odds"] = 0.85
                warnings.append("1X2 market present, but secondary totals/btts incomplete")
        else:
            scores["odds"] = 0.40
            warnings.append("Odds snapshot present, but 1X2 market is incomplete or non-normalized")
    else:
        scores["odds"] = 0.0
        missing_fields.append({"field": "odds", "reason": "No odds snapshot set <= as_of"})
        warnings.append("No odds snapshot available")
    active_weights["odds"] = w.odds

    # 6. Research
    if evidence.research is not None:
        r_status = evidence.research.status
        if r_status == ResearchState.AVAILABLE.value:
            scores["research"] = 1.0
        elif r_status == ResearchState.NO_USEFUL_RESULTS.value:
            scores["research"] = 0.85
        elif r_status == ResearchState.DISABLED.value:
            scores["research"] = 0.70
        elif r_status == ResearchState.EXTRACTION_UNAVAILABLE.value:
            scores["research"] = 0.60
            warnings.append("Web research extraction unavailable")
        elif r_status == ResearchState.QUOTA_DENIED.value:
            scores["research"] = 0.40
            warnings.append("Web research quota was denied")
        elif r_status == ResearchState.PROVIDER_ERROR.value:
            scores["research"] = 0.20
            provider_errors.append({"source": "research", "status": "PROVIDER_ERROR"})
            warnings.append("Web research encountered provider error")
        else:
            scores["research"] = 0.50

        # Research conflicts
        if evidence.research.conflicts_count > 0:
            conflicts.append(
                {
                    "source": "research_claims",
                    "conflicts_count": evidence.research.conflicts_count,
                }
            )
    else:
        scores["research"] = 0.50
    active_weights["research"] = w.research

    # 7. Lineups (Phase-dependent policy)
    if evidence.forecast_phase == ForecastPhase.MORNING:
        # MORNING policy: Lineups are N/A and excluded from denominator
        scores["lineups"] = 1.0  # Or record 1.0 / N/A, weight is 0.0 so not counted in denominator
    else:
        # PREMATCH policy: Evaluated per publication/freshness
        active_weights["lineups"] = w.lineups
        if features.lineups_both_confirmed:
            scores["lineups"] = 1.0
        elif (
            features.home_lineup_publication_state == "PUBLISHED"
            and features.away_lineup_publication_state == "PUBLISHED"
        ):
            scores["lineups"] = 0.75
            warnings.append("Lineups published but unconfirmed by one or both teams")
        elif (
            features.home_lineup_publication_state == "PUBLISHED"
            or features.away_lineup_publication_state == "PUBLISHED"
        ):
            scores["lineups"] = 0.50
            warnings.append("Lineup published for only one team")
        else:
            scores["lineups"] = 0.30
            warnings.append("Lineups not yet published in PREMATCH phase")

    # Conflict penalties
    conflict_penalty = min(0.20, len(conflicts) * 0.05)
    provider_error_penalty = min(0.20, len(provider_errors) * 0.10)

    total_weight = sum(active_weights.values())
    weighted_sum = sum(scores[dim] * active_weights[dim] for dim in active_weights)
    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall = max(0.0, min(1.0, base_score - conflict_penalty - provider_error_penalty))
    overall_score = round(overall, 4)

    # Determine Quality Band
    if overall_score >= 0.90:
        band = "excellent"
    elif overall_score >= 0.80:
        band = "good"
    elif overall_score >= 0.65:
        band = "usable_with_warnings"
    else:
        band = "abstain"

    # Critical missing checks
    if scores["odds"] == 0.0 and scores["form"] == 0.0:
        critical_missing.append("both_odds_and_form_missing")

    can_predict = (overall_score >= min_predict_score) and (len(critical_missing) == 0)

    as_of_str = (
        evidence.as_of.astimezone(UTC).isoformat()
        if evidence.as_of.tzinfo
        else evidence.as_of.replace(tzinfo=UTC).isoformat()
    )

    return QualityReportData(
        schema_version="quality_v1",
        forecast_phase=evidence.forecast_phase.value,
        as_of=as_of_str,
        overall_score=overall_score,
        quality_band=band,
        can_predict=can_predict,
        dimension_scores={k: round(v, 4) for k, v in scores.items()},
        critical_missing=critical_missing,
        missing_fields=missing_fields,
        warnings=warnings,
        conflicts=conflicts,
        provider_errors=provider_errors,
        stale_sources=stale_sources,
        source_manifest=manifest.to_dict(),
    )
