from __future__ import annotations

import socket
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.models import JobAttempt

logger = get_logger(__name__)


def _safe_error_class(exc: BaseException | None) -> str | None:
    """Return a redacted exception class name. Never persist full
    exception messages — they may contain secrets, PII, stack traces."""
    if exc is None:
        return None
    cls = type(exc).__name__
    if len(cls) > 128:
        return cls[:128]
    return cls


async def record_job_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    job_id: uuid.UUID,
    attempt_number: int,
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    error: BaseException | None = None,
) -> None:
    """Insert a `job_attempts` row reflecting one worker execution.

    Closes the M4 debt. Only class names are persisted (no full
    exception messages) to keep secrets and stack traces out of the DB.
    """
    try:
        async with session_factory() as session:
            session.add(
                JobAttempt(
                    job_id=job_id,
                    attempt_number=attempt_number,
                    worker=f"{socket.gethostname()}:pid",
                    started_at=started_at,
                    finished_at=finished_at,
                    status=outcome,
                    error_class=_safe_error_class(error),
                    error_message_redacted=None,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("failed to persist job_attempts row", exc_info=True)
