from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.models import JobAttempt

logger = get_logger(__name__)

_MAX_ATTEMPT_INSERT_RETRIES = 3


def worker_identity() -> str:
    """hostname:pid — the real OS pid, never a literal placeholder."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _safe_error_class(exc: BaseException | None) -> str | None:
    """Return a redacted exception class name. Never persist full
    exception messages — they may contain secrets, PII, stack traces."""
    if exc is None:
        return None
    cls = type(exc).__name__
    return cls[:128]


async def _next_attempt_number(session: AsyncSession, job_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.max(JobAttempt.attempt_number), 0)).where(
        JobAttempt.job_id == job_id
    )
    current = (await session.execute(stmt)).scalar_one()
    return int(current) + 1


async def record_job_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    job_id: uuid.UUID,
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    error: BaseException | None = None,
) -> int:
    """Insert a `job_attempts` row reflecting one worker execution.

    The attempt number is derived per job (requeue/retry → 1, 2, 3…).
    Unique-violation races are retried with a re-read; exhaustion raises
    instead of silently pretending the attempt was recorded. Only class
    names are persisted (no full exception messages) to keep secrets and
    stack traces out of the DB.

    Returns the persisted attempt number.
    """
    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPT_INSERT_RETRIES):
        try:
            async with session_factory() as session, session.begin():
                attempt_number = await _next_attempt_number(session, job_id)
                session.add(
                    JobAttempt(
                        job_id=job_id,
                        attempt_number=attempt_number,
                        worker=worker_identity(),
                        started_at=started_at,
                        finished_at=finished_at,
                        status=outcome,
                        error_class=_safe_error_class(error),
                        error_message_redacted=None,
                    )
                )
            return attempt_number
        except IntegrityError as exc:
            last_error = exc
    # Do NOT swallow uniqueness conflicts: loud failure.
    logger.error(
        "failed to persist job_attempts row after retries",
        exc_info=last_error,
        extra={"job_id": str(job_id)},
    )
    raise RuntimeError(f"could not record job attempt for job {job_id}") from last_error
