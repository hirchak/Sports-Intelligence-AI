import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC
from typing import Any

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.context.provenance import SourceManifest
from sports_intelligence.context.selector import SelectedEvidence
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory, ResearchState
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
class QualityPolicy:
    policy_version: str = "quality_policy_v1"
    weights: QualityWeights = field(default_factory=QualityWeights)
    min_predict_score: float = 0.65
    band_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "excellent": 0.90,
            "good": 0.80,
            "usable_with_warnings": 0.65,
        }
    )
    staleness_penalty: float = 0.05
    max_staleness_penalty: float = 0.20

    def __post_init__(self) -> None:
        w_dict = asdict(self.weights)
        for k, v in w_dict.items():
            if v < 0:
                raise ValueError(f"Quality weight '{k}' must be >= 0, got {v}")
        total = sum(w_dict.values())
        if total <= 0:
            raise ValueError(f"Total quality weight must be > 0, got {total}")
        if not (0.0 <= self.min_predict_score <= 1.0):
            raise ValueError(
                f"min_predict_score must be between 0 and 1, got {self.min_predict_score}"
            )
        usable = self.band_thresholds.get("usable_with_warnings", 0.0)
        good = self.band_thresholds.get("good", 0.0)
        excellent = self.band_thresholds.get("excellent", 0.0)
        if not (0.0 <= usable <= good <= excellent <= 1.0):
            raise ValueError(
                "Quality band thresholds must satisfy 0 <= usable <= good <= excellent <= 1, "
                f"got usable={usable}, good={good}, excellent={excellent}"
            )
        if self.staleness_penalty < 0:
            raise ValueError(f"staleness_penalty must be >= 0, got {self.staleness_penalty}")
        if not (0.0 <= self.max_staleness_penalty <= 1.0):
            raise ValueError(
                f"max_staleness_penalty must be between 0 and 1, got {self.max_staleness_penalty}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "weights": asdict(self.weights),
            "min_predict_score": self.min_predict_score,
            "band_thresholds": self.band_thresholds,
            "staleness_penalty": self.staleness_penalty,
            "max_staleness_penalty": self.max_staleness_penalty,
        }

    def policy_fingerprint(self) -> str:
        data = self.to_dict()
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def build_quality_policy(settings: Settings) -> QualityPolicy:
    weights = QualityWeights(
        fixture_identity=settings.quality_weight_fixture_identity,
        form=settings.quality_weight_form,
        season_stats=settings.quality_weight_season_stats,
        availability=settings.quality_weight_availability,
        odds=settings.quality_weight_odds,
        research=settings.quality_weight_research,
        lineups=settings.quality_weight_lineups,
    )
    band_thresholds = {
        "excellent": settings.quality_band_excellent_min,
        "good": settings.quality_band_good_min,
        "usable_with_warnings": settings.quality_band_usable_min,
    }
    return QualityPolicy(
        policy_version="quality_policy_v1",
        weights=weights,
        min_predict_score=settings.quality_min_predict_score,
        band_thresholds=band_thresholds,
        staleness_penalty=settings.quality_staleness_penalty,
        max_staleness_penalty=settings.quality_max_staleness_penalty,
    )


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
    source_fingerprint: str | None = None
    quality_policy: dict[str, Any] = field(default_factory=dict)
    policy_fingerprint: str | None = None
    freshness_policy: dict[str, Any] = field(default_factory=dict)
    freshness_policy_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_data_quality(
    evidence: SelectedEvidence,
    features: DeterministicFeatures,
    manifest: SourceManifest,
    *,
    weights: QualityWeights | None = None,
    min_predict_score: float = 0.65,
    policy: QualityPolicy | None = None,
    freshness_policy: FreshnessPolicy | None = None,
) -> QualityReportData:
    """Deterministic Data Quality Engine evaluating evidence completeness, freshness, and conflicts.

    Rules:
    - Pure calculation, zero external API calls.
    - Evaluates point-in-time freshness against configured phase TTLs.
    - MORNING phase excludes Lineups dimension from score denominator (Lineups = N/A).
    - PREMATCH phase evaluates canonical publication states: CONFIRMED,
      NOT_YET_PUBLISHED, UNSUPPORTED, PROVIDER_ERROR.
    - Distinguishes not-collected research from NO_USEFUL_RESULTS.
    - Configurable dimension weights, bands, and prediction threshold persisted with report.
    """
    q_policy = policy or QualityPolicy(
        weights=weights or QualityWeights(), min_predict_score=min_predict_score
    )
    w = q_policy.weights
    scores: dict[str, float] = {}
    active_weights: dict[str, float] = {}
    critical_missing: list[str] = []
    missing_fields: list[dict[str, Any]] = []
    warnings: list[str] = []
    conflicts: list[dict[str, Any]] = []
    provider_errors: list[dict[str, Any]] = []
    stale_sources: list[str] = []

    as_of_aware = (
        evidence.as_of.astimezone(UTC)
        if evidence.as_of.tzinfo
        else evidence.as_of.replace(tzinfo=UTC)
    )

    f_policy = freshness_policy if freshness_policy is not None else FreshnessPolicy(Settings())

    # Evaluate Freshness at as_of
    if evidence.standings is not None and f_policy.is_stale(
        FreshnessCategory.STANDINGS,
        evidence.standings.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("standings")
        warnings.append("Standings snapshot exceeds freshness TTL")

    if evidence.home_team_stats is not None and f_policy.is_stale(
        FreshnessCategory.TEAM_STATISTICS,
        evidence.home_team_stats.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("home_team_statistics")
        warnings.append("Home team statistics snapshot exceeds freshness TTL")

    if evidence.away_team_stats is not None and f_policy.is_stale(
        FreshnessCategory.TEAM_STATISTICS,
        evidence.away_team_stats.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("away_team_statistics")
        warnings.append("Away team statistics snapshot exceeds freshness TTL")

    if evidence.home_form is not None and f_policy.is_stale(
        FreshnessCategory.TEAM_FORM,
        evidence.home_form.as_of,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("home_team_form")
        warnings.append("Home team form snapshot exceeds freshness TTL")

    if evidence.away_form is not None and f_policy.is_stale(
        FreshnessCategory.TEAM_FORM,
        evidence.away_form.as_of,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("away_team_form")
        warnings.append("Away team form snapshot exceeds freshness TTL")

    if evidence.home_availability is not None and f_policy.is_stale(
        FreshnessCategory.AVAILABILITY,
        evidence.home_availability.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("home_availability")
        warnings.append("Home availability snapshot exceeds freshness TTL")

    if evidence.away_availability is not None and f_policy.is_stale(
        FreshnessCategory.AVAILABILITY,
        evidence.away_availability.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("away_availability")
        warnings.append("Away availability snapshot exceeds freshness TTL")

    if evidence.odds_set is not None and f_policy.is_stale(
        FreshnessCategory.ODDS,
        evidence.odds_set.captured_at,
        as_of_aware,
        evidence.forecast_phase,
    ):
        stale_sources.append("odds")
        warnings.append("Odds snapshot set exceeds freshness TTL")

    if (
        evidence.research is not None
        and evidence.research.last_captured_at is not None
        and f_policy.is_stale(
            FreshnessCategory.RESEARCH,
            evidence.research.last_captured_at,
            as_of_aware,
            evidence.forecast_phase,
        )
    ):
        stale_sources.append("research")
        warnings.append("Research snapshot exceeds freshness TTL")

    if evidence.forecast_phase != ForecastPhase.MORNING:
        if evidence.home_lineup is not None and f_policy.is_stale(
            FreshnessCategory.LINEUPS,
            evidence.home_lineup.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale_sources.append("home_lineup")
            warnings.append("Home lineup snapshot exceeds freshness TTL")

        if evidence.away_lineup is not None and f_policy.is_stale(
            FreshnessCategory.LINEUPS,
            evidence.away_lineup.captured_at,
            as_of_aware,
            evidence.forecast_phase,
        ):
            stale_sources.append("away_lineup")
            warnings.append("Away lineup snapshot exceeds freshness TTL")

    # 1. Fixture Identity
    fix = evidence.fixture
    if (
        fix.kickoff_at is None
        or fix.home_team_id is None
        or fix.away_team_id is None
        or fix.fixture_metadata_snapshot_id is None
        or fix.status == "METADATA_UNAVAILABLE"
        or evidence.fixture_metadata is None
    ):
        scores["fixture_identity"] = 0.0
        if (
            fix.fixture_metadata_snapshot_id is None
            or fix.status == "METADATA_UNAVAILABLE"
            or evidence.fixture_metadata is None
        ):
            critical_missing.append("fixture_metadata_missing")
            missing_fields.append(
                {
                    "field": "fixture_metadata",
                    "reason": "Missing immutable fixture metadata snapshot <= as_of",
                }
            )
            warnings.append(
                "Fixture metadata snapshot missing <= as_of; status is METADATA_UNAVAILABLE"
            )
        else:
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

    if fix.league_name is None or fix.league_slug is None:
        warnings.append(
            "Observed league display identity unavailable in historical metadata snapshot"
        )
        missing_fields.append(
            {
                "field": "observed_league_display",
                "reason": "Missing observed league name or slug in metadata snapshot",
            }
        )

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
        if evidence.research.run_id is None and r_status == ResearchState.NO_USEFUL_RESULTS.value:
            scores["research"] = 0.50
            warnings.append("No research run has been collected for this fixture")
        elif r_status == ResearchState.AVAILABLE.value:
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
        warnings.append("Research evidence not available")
    active_weights["research"] = w.research

    # 7. Lineups (Phase-dependent policy)
    if evidence.forecast_phase == ForecastPhase.MORNING:
        # MORNING policy: Lineups are N/A and excluded from denominator
        scores["lineups"] = 1.0
    else:
        # PREMATCH policy: Canonical states CONFIRMED, NOT_YET_PUBLISHED,
        # UNSUPPORTED, PROVIDER_ERROR
        active_weights["lineups"] = w.lineups
        h_pub = features.home_lineup_publication_state or "NOT_YET_PUBLISHED"
        a_pub = features.away_lineup_publication_state or "NOT_YET_PUBLISHED"

        if "PROVIDER_ERROR" in (h_pub, a_pub):
            scores["lineups"] = 0.20
            provider_errors.append({"source": "lineups", "status": "PROVIDER_ERROR"})
            warnings.append("Lineup collection encountered provider error")
        elif "UNSUPPORTED" in (h_pub, a_pub):
            scores["lineups"] = 0.50
            warnings.append("Lineups are unsupported for this fixture or league")
        elif features.lineups_both_confirmed or (h_pub == "CONFIRMED" and a_pub == "CONFIRMED"):
            scores["lineups"] = 1.0
        elif h_pub == "CONFIRMED" or a_pub == "CONFIRMED":
            scores["lineups"] = 0.70
            warnings.append("Lineup confirmed for only one team")
        elif h_pub == "NOT_YET_PUBLISHED" and a_pub == "NOT_YET_PUBLISHED":
            scores["lineups"] = 0.40
            warnings.append("Lineups not yet published in PREMATCH phase")
        else:
            scores["lineups"] = 0.40
            warnings.append(f"Unconfirmed lineup states: home={h_pub}, away={a_pub}")

    # Penalties
    conflict_penalty = min(0.20, len(conflicts) * 0.05)
    provider_error_penalty = min(0.20, len(provider_errors) * 0.10)
    staleness_penalty = min(
        q_policy.max_staleness_penalty, len(stale_sources) * q_policy.staleness_penalty
    )

    total_weight = sum(active_weights.values())
    weighted_sum = sum(scores[dim] * active_weights[dim] for dim in active_weights)
    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall = max(
        0.0,
        min(1.0, base_score - conflict_penalty - provider_error_penalty - staleness_penalty),
    )
    overall_score = round(overall, 4)

    # Critical missing checks
    if scores.get("odds", 0.0) == 0.0 and scores.get("form", 0.0) == 0.0:
        critical_missing.append("both_odds_and_form_missing")

    # Determine Quality Band per policy thresholds
    band_th = q_policy.band_thresholds
    if len(critical_missing) > 0 or "fixture_metadata_missing" in critical_missing:
        band = "abstain"
    elif overall_score >= band_th.get("excellent", 0.90):
        band = "excellent"
    elif overall_score >= band_th.get("good", 0.80):
        band = "good"
    elif overall_score >= band_th.get("usable_with_warnings", 0.65):
        band = "usable_with_warnings"
    else:
        band = "abstain"

    can_predict = (overall_score >= q_policy.min_predict_score) and (len(critical_missing) == 0)

    as_of_str = as_of_aware.isoformat()

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
        source_fingerprint=manifest.source_fingerprint,
        quality_policy=q_policy.to_dict(),
        policy_fingerprint=q_policy.policy_fingerprint(),
        freshness_policy=f_policy.to_dict(),
        freshness_policy_fingerprint=f_policy.policy_fingerprint(),
    )
