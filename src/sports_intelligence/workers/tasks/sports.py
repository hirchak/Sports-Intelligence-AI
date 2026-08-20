from __future__ import annotations

import asyncio
from datetime import date

from sports_intelligence.core.config import get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import (
    FixtureDiscoveryService,
    update_job_status,
)
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="sports.discover_fixtures", queue="sports_io")  # type: ignore[untyped-decorator]
def discover_fixtures_task(job_id: str, fixture_date: str) -> dict[str, object]:
    return asyncio.run(_run_discovery(job_id, fixture_date))


async def _run_discovery(job_id: str, fixture_date: str) -> dict[str, object]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    provider = build_sports_provider(settings)
    league_config = load_league_config(settings.leagues_config_path)
    service = FixtureDiscoveryService(
        provider=provider,
        session_factory=session_factory,
        league_config=league_config,
        app_timezone=settings.app_timezone,
    )
    try:
        async with session_factory() as session:
            await update_job_status(session, job_id, JobStatus.RUNNING)
            await session.commit()
        summary = await service.discover(date.fromisoformat(fixture_date))
        async with session_factory() as session:
            await update_job_status(session, job_id, JobStatus.SUCCEEDED)
            await session.commit()
        return {"job_id": job_id, **summary.model_dump(mode="json")}
    except Exception:
        logger.exception("fixture discovery job failed", extra={"job_id": job_id})
        async with session_factory() as session:
            await update_job_status(session, job_id, JobStatus.FAILED)
            await session.commit()
        raise
    finally:
        await provider.aclose()
        await engine.dispose()
