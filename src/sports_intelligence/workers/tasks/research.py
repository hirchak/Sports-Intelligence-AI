from __future__ import annotations

import asyncio
import json

from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.tasks.collect import _run_collect_job


@celery_app.task(name="research.collect", queue="research_io")  # type: ignore[untyped-decorator]
def research_collect_task(
    job_id: str,
    fixture_id: str,
    phase: str = ForecastPhase.MORNING.value,
    estimated_cost: int = 6,
) -> dict[str, object]:
    """Dedicated Celery task for web research running on queue 'research_io'."""
    return asyncio.run(
        _run_collect_job(
            job_id=job_id,
            collector_name="research",
            inputs_json=json.dumps({"fixture_id": fixture_id}),
            phase=phase,
            estimated_cost=estimated_cost,
        )
    )
