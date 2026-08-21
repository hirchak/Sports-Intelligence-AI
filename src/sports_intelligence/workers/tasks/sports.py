from __future__ import annotations

import asyncio
from datetime import date

from sports_intelligence.core.config import get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import (
    LeagueConfigVersionMismatchError,
    load_league_config,
)
from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import (
    FixtureDiscoveryService,
    update_job_status,
)
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="sports.discover_fixtures", queue="sports_io")  # type: ignore[untyped-decorator]
def discover_fixtures_task(
    job_id: str,
    fixture_date: str,
    expected_league_config_version: int,
    discovery_timezone: str,
) -> dict[str, object]:
    return asyncio.run(
        _run_discovery(job_id, fixture_date, expected_league_config_version, discovery_timezone)
    )


async def _run_discovery(
    job_id: str,
    fixture_date: str,
    expected_league_config_version: int,
    discovery_timezone: str,
) -> dict[str, object]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    provider: SportsDataProvider | None = None
    try:
        league_config = load_league_config(settings.leagues_config_path)
        if league_config.version != expected_league_config_version:
            raise LeagueConfigVersionMismatchError(
                expected=expected_league_config_version,
                actual=league_config.version,
            )
        provider = build_sports_provider(settings)
        service = FixtureDiscoveryService(
            provider=provider,
            session_factory=session_factory,
            league_config=league_config,
            app_timezone=discovery_timezone,
        )

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
        try:
            async with session_factory() as session:
                await update_job_status(session, job_id, JobStatus.FAILED)
                await session.commit()
        except Exception:
            logger.warning(
                "failed to mark discovery job as FAILED",
                exc_info=True,
                extra={"job_id": job_id},
            )
        raise
    finally:
        if provider is not None:
            try:
                await provider.aclose()
            except Exception:
                logger.warning("provider cleanup failed", exc_info=True)
        try:
            await engine.dispose()
        except Exception:
            logger.warning("engine cleanup failed during discovery", exc_info=True)
