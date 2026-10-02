from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.db.models import (
    Experiment,
    ExperimentArm,
    ExperimentCall,
    ExperimentCase,
    ExperimentComparison,
    ExperimentPrediction,
    ExperimentRun,
    FixtureResult,
)
from sports_intelligence.evaluation.metrics import calibration
from sports_intelligence.evaluation.service import Aggregate, aggregate_values
from sports_intelligence.evaluation.settlement import (
    Outcome,
    ResultObservation,
    fixed_return,
    settle,
)
from sports_intelligence.experiments.contracts import ExperimentDefinition
from sports_intelligence.experiments.service import change_run_state
from sports_intelligence.predictions.contracts import MARKETS, Selection


def measure(group: Aggregate, definition: ExperimentDefinition) -> dict[str, Any]:
    return {
        "metrics": {
            n: {"value": v, "sample_size": count}
            for n, (v, count) in aggregate_values(group, definition.evaluation).items()
        },
        "calibration": [asdict(b) for b in calibration(group.samples, definition.evaluation)],
    }


def add_samples(
    group: Aggregate,
    prediction: ExperimentPrediction,
    result: ResultObservation | None,
    definition: ExperimentDefinition,
    source: str = "llm",
    allowed: set[str] | None = None,
) -> set[str]:
    selected = set()
    baseline = next((b for b in prediction.baselines_jsonb if b["name"] == source), None)
    for selection, stored_probability in prediction.probabilities_jsonb.items():
        p: float | None = stored_probability
        if MARKETS[Selection(selection)] not in definition.population.markets:
            continue
        if allowed is not None and selection not in allowed:
            continue
        outcome = (
            settle(Selection(selection), result, definition.evaluation.settlement_version)
            if result
            else Outcome.UNSETTLED
        )
        if outcome not in (Outcome.WIN, Outcome.LOSS):
            continue
        if source != "llm":
            p = baseline["probabilities"].get(selection) if baseline else None
        if p is None:
            group.missing_baseline += 1
            continue
        y = int(outcome == Outcome.WIN)
        group.samples.append((p, y))
        group.evaluated_runs.add(prediction.case_id)
        selected.add(selection)
        if selection in ("HOME", "DRAW", "AWAY"):
            group.classes.setdefault((str(prediction.case_id), source), {})[selection] = (p, y)
    if source == "llm":
        for c in prediction.candidates_jsonb:
            if (
                not c["displayed"]
                or MARKETS[Selection(c["selection"])] not in definition.population.markets
            ):
                continue
            if allowed is not None and c["selection"] not in allowed:
                continue
            group.displayed_runs.add(prediction.case_id)
            outcome = settle(Selection(c["selection"]), result) if result else Outcome.UNSETTLED
            group.candidates.append(
                (
                    outcome,
                    c["captured_odds"],
                    fixed_return(outcome, c["captured_odds"]),
                    c["expected_value"],
                    None,
                )
            )
    return selected


async def compare_run(session: AsyncSession, run_id: UUID) -> ExperimentComparison:
    run = await session.scalar(
        select(ExperimentRun).where(ExperimentRun.id == run_id).with_for_update()
    )
    if run is None:
        raise ValueError("run_not_found")
    prior = await session.scalar(
        select(ExperimentComparison).where(ExperimentComparison.run_id == run_id)
    )
    if prior:
        return prior
    if run.status != "RUNNING":
        raise ValueError("run_not_ready_for_comparison")
    experiment = await session.get(Experiment, run.experiment_id)
    assert experiment is not None
    definition = ExperimentDefinition.model_validate(experiment.definition_jsonb)
    cases = list(
        (
            await session.scalars(
                select(ExperimentCase)
                .where(ExperimentCase.run_id == run_id)
                .order_by(ExperimentCase.ordinal)
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(ExperimentPrediction, ExperimentArm)
            .join(ExperimentArm)
            .where(ExperimentPrediction.case_id.in_([c.id for c in cases]))
        )
    ).all()
    if any(p.status in ("RUNNING", "QUEUED") for p, _ in rows):
        raise ValueError("experiment_outputs_in_flight")
    outputs = {(p.case_id, a.name): p for p, a in rows}
    result_ids = {c.result_id for c in cases if c.result_id}
    results = {
        r.id: ResultObservation.model_validate(r.normalized_jsonb)
        for r in (
            await session.scalars(select(FixtureResult).where(FixtureResult.id.in_(result_ids)))
        ).all()
    }
    call_map: dict[UUID, list[ExperimentCall]] = {}
    for call in (
        await session.scalars(select(ExperimentCall).where(ExperimentCall.run_id == run_id))
    ).all():
        call_map.setdefault(call.prediction_id, []).append(call)
    groups = {
        n: Aggregate({"arm": n})
        for n in (
            "control",
            "treatment",
            "paired_control",
            "paired_treatment",
            "market",
            "statistical",
        )
    }
    counts = dict(run.counts_jsonb)
    counts.update(
        executed=0,
        predicted=0,
        settled=0,
        evaluated=0,
        paired=0,
        failed_control=0,
        failed_treatment=0,
        abstained_control=0,
        abstained_treatment=0,
        missing_result=0,
    )
    reasons = Counter(counts["reasons"])
    settlement_manifest = []
    for case in cases:
        result = results.get(case.result_id) if case.result_id else None
        selected = {}
        for name in ("control", "treatment"):
            p = outputs.get((case.id, name))
            if p is None:
                continue
            counts["executed"] += 1
            groups[name].coverage_available = True
            groups[name].statuses[p.status].add(case.id)
            counts["failed_" + name] += p.status == "FAILED"
            counts["abstained_" + name] += p.status == "ABSTAINED"
            if p.reason:
                reasons[name + ":" + p.reason] += 1
            if p.status == "SUCCEEDED":
                counts["predicted"] += 1
                selected[name] = add_samples(groups[name], p, result, definition)
                counts["evaluated"] += bool(selected[name])
                counts["settled"] += bool(
                    result
                    and any(
                        settle(Selection(s), result) != Outcome.UNSETTLED
                        for s in p.probabilities_jsonb
                    )
                )
                settlement_manifest.append(
                    {
                        "prediction_id": str(p.id),
                        "result_id": str(case.result_id) if case.result_id else None,
                        "outcomes": {
                            s: settle(Selection(s), result).value if result else "UNSETTLED"
                            for s in p.probabilities_jsonb
                        },
                    }
                )
                if name == "control":
                    for source in ("market", "statistical"):
                        add_samples(groups[source], p, result, definition, source)
            calls = call_map.get(p.id, [])
            for field, target in (
                ("latency_ms", groups[name].latency),
                ("input_tokens", groups[name].input_tokens),
                ("output_tokens", groups[name].output_tokens),
            ):
                values = [(c.result_jsonb or {}).get(field) for c in calls]
                known = [float(x) for x in values if x is not None]
                if known:
                    target.append(sum(known))
                elif p.actual_identity_jsonb.get("telemetry", {}).get(field) is not None:
                    target.append(float(p.actual_identity_jsonb["telemetry"][field]))
        if case.status == "ELIGIBLE" and not result:
            counts["missing_result"] += 1
            reasons["missing_result"] += 1
        intersection = selected.get("control", set()) & selected.get("treatment", set())
        if intersection:
            counts["paired"] += 1
            for name in ("control", "treatment"):
                p = outputs[(case.id, name)]
                group = groups["paired_" + name]
                group.coverage_available = True
                group.statuses["SUCCEEDED"].add(case.id)
                add_samples(group, p, result, definition, allowed=intersection)
    counts["reasons"] = dict(sorted(reasons.items()))
    measures = {name: measure(group, definition) for name, group in groups.items()}
    deltas = {}
    for key, row in measures["paired_control"]["metrics"].items():
        other = measures["paired_treatment"]["metrics"].get(key)
        if other and row["value"] is not None and other["value"] is not None:
            deltas[key] = {
                "treatment_minus_control": other["value"] - row["value"],
                "sample_size": min(row["sample_size"], other["sample_size"]),
            }
    interpretation = (
        "MEASURED_ONLY"
        if counts["paired"] >= definition.min_paired_fixtures
        else "INSUFFICIENT_SAMPLE"
    )
    limitations = [
        "Measurements only; no significance, causal superiority or production promotion.",
        "Markets from a fixture are correlated; minimum sample uses fixture pairs.",
        "No monetary cost known; closing proxy unavailable unless separately measured.",
        "Baseline metrics use the control population; missing baseline probabilities reduce n.",
    ]
    if any(a.source != "replay" for a in (definition.control, definition.treatment)):
        limitations.append(
            "Historical arm reuses recorded forecast/telemetry; no new model call for that arm."
        )
    if definition.control.phase != definition.treatment.phase:
        limitations.append(
            "Different phases have different information availability; observational comparison."
        )
    if definition.control.variant != definition.treatment.variant:
        limitations.append("WITHOUT_ODDS also masks research; not a pure causal odds experiment.")
    summary = {
        "counts": counts,
        "interpretation": interpretation,
        "min_paired_fixtures": definition.min_paired_fixtures,
        "groups": measures,
        "paired_deltas": deltas,
        "paired_population": "intersection of successful, settled selections on both fixture arms",
        "limitations": limitations,
        "definition_hash": experiment.definition_hash,
        "manifest_hash": run.manifest_hash,
        "evaluation": definition.evaluation.model_dump(mode="json"),
        "settlement_manifest": settlement_manifest,
        "monetary_cost": None,
    }
    comparison = ExperimentComparison(
        run_id=run.id, evaluation_version=definition.evaluation.version, summary_jsonb=summary
    )
    session.add(comparison)
    run.counts_jsonb = counts
    target_status = (
        "FAILED"
        if counts["failed_control"] or counts["failed_treatment"]
        else "INSUFFICIENT_DATA"
        if not counts["paired"]
        else "SUCCEEDED"
    )
    await change_run_state(session, run, target_status, "comparison_worker")
    await session.flush()
    return comparison
