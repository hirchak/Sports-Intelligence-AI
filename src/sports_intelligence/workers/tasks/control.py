from __future__ import annotations

from sports_intelligence.core.time import utc_now
from sports_intelligence.workers.celery_app import celery_app


@celery_app.task(name="control.ping", queue="control")  # type: ignore[untyped-decorator]
def ping(correlation_id: str | None = None) -> dict[str, object]:
    return {
        "pong": True,
        "timestamp": utc_now().isoformat(),
        "correlation_id": correlation_id,
    }
