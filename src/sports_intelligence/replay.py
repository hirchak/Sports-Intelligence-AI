"""Local CLI: plan by default; execution queues bounded worker jobs."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sports_intelligence.core.config import get_settings
from sports_intelligence.db.models import Experiment
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.experiments.contracts import ExperimentDefinition, RunRequest
from sports_intelligence.experiments.planner import plan_replay
from sports_intelligence.experiments.service import create_experiment, enqueue_run, request_run


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Frozen historical replay: plan by default, no provider backfill."
    )
    p.add_argument(
        "--experiment", required=True, help="Experiment UUID or strict definition JSON file"
    )
    p.add_argument("--from", dest="start", type=date.fromisoformat)
    p.add_argument("--to", dest="end", type=date.fromisoformat, help="Inclusive UTC date")
    p.add_argument("--phase", choices=("MORNING", "PREMATCH"))
    p.add_argument("--league", action="append", type=UUID)
    p.add_argument("--context", action="append", type=UUID, help="Exact frozen context identity")
    p.add_argument("--model-route", help="Configured treatment route")
    p.add_argument("--prompt", choices=("default", "candidate"))
    p.add_argument("--variant", choices=("LLM_WITH_ODDS", "LLM_WITHOUT_ODDS"))
    p.add_argument("--max-fixtures", type=int)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--execute", action="store_true", help="Explicitly queue execution")
    p.add_argument("--dry-run", "--plan", action="store_true", dest="dry_run")
    p.add_argument("--mock", action="store_true", help="Refuse any non-mock frozen route")
    p.add_argument(
        "--live-opt-in", action="store_true", help="Requires LIVE_LOCAL and explicit env enable"
    )
    p.add_argument("--rerun-key", type=UUID)
    return p


async def replay(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            try:
                identity = UUID(args.experiment)
            except ValueError:
                data = json.loads(Path(args.experiment).read_text())
                pop = data["population"]
                treatment = data.setdefault("treatment", {})
                if args.start:
                    pop["start"] = datetime.combine(
                        args.start, datetime.min.time(), UTC
                    ).isoformat()
                if args.end:
                    pop["end"] = datetime.combine(
                        args.end + timedelta(days=1), datetime.min.time(), UTC
                    ).isoformat()
                if args.context:
                    pop["context_ids"] = [str(x) for x in args.context]
                if args.league:
                    pop["league_ids"] = [str(x) for x in args.league]
                if args.phase:
                    data.setdefault("control", {})["phase"] = treatment["phase"] = args.phase
                for flag, key in (
                    ("model_route", "route"),
                    ("prompt", "prompt"),
                    ("variant", "variant"),
                ):
                    if getattr(args, flag):
                        treatment[key] = getattr(args, flag)
                if args.max_fixtures is not None:
                    data["max_fixtures"] = args.max_fixtures
                if args.max_calls is not None:
                    data["max_llm_calls"] = args.max_calls
                experiment, _ = await create_experiment(
                    session, ExperimentDefinition.model_validate(data), settings
                )
                await session.commit()
            else:
                if any(
                    getattr(args, n) is not None
                    for n in (
                        "start",
                        "end",
                        "league",
                        "context",
                        "phase",
                        "model_route",
                        "prompt",
                        "variant",
                        "max_fixtures",
                        "max_calls",
                    )
                ):
                    raise ValueError(
                        "existing_definition_is_immutable_use_definition_file_for_changes"
                    )
                existing = await session.get(Experiment, identity)
                if existing is None:
                    raise ValueError("experiment_not_found")
                experiment = existing
            if args.mock:
                from sqlalchemy import select

                from sports_intelligence.db.models import ExperimentArm

                arms = (
                    await session.scalars(
                        select(ExperimentArm).where(ExperimentArm.experiment_id == experiment.id)
                    )
                ).all()
                if any(m["provider"] != "mock" for a in arms for m in a.frozen_jsonb["models"]):
                    raise ValueError("mock_requested_but_live_arm_configured")
            plan = await plan_replay(
                session, ExperimentDefinition.model_validate(experiment.definition_jsonb)
            )
            answer = {
                "experiment_id": str(experiment.id),
                "status": plan["status"],
                "counts": plan["counts"],
                "estimated_initial_calls": plan["counts"]["eligible"]
                * sum(
                    arm["source"] == "replay"
                    for arm in (
                        experiment.definition_jsonb["control"],
                        experiment.definition_jsonb["treatment"],
                    )
                ),
            }
            if args.execute and not args.dry_run:
                run, created = await request_run(
                    session,
                    experiment,
                    RunRequest(rerun_key=args.rerun_key, live_opt_in=args.live_opt_in),
                    settings,
                )
                await enqueue_run(session, run, created)
                answer.update(run_id=str(run.id), status=run.status, already_queued=not created)
            return answer
    finally:
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(replay(args)), sort_keys=True))
    except (ValueError, OSError):
        raise SystemExit(
            "Replay refused: invalid definition/scope/configuration or unavailable historical plan."
        ) from None


if __name__ == "__main__":
    main()
