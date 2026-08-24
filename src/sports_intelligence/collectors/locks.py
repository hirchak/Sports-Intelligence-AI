from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis

from sports_intelligence.core.config import Settings


@dataclass
class CoalesceLock:
    key: str
    token: str


class CoalesceLockManager:
    """Redis-backed request coalescing (spec 11 §7).

    Equivalent external requests share one provider call: the first
    winner acquires the lock, fetches, releases; concurrent waiters
    poll for the cached result under a companion key (best-effort).
    """

    _RELEASE_SCRIPT = (
        "if redis.call('GET', KEYS[1]) == ARGV[1] then "
        "return redis.call('DEL', KEYS[1]) else return 0 end"
    )

    def __init__(
        self,
        redis: Redis,
        settings: Settings,
    ) -> None:
        self._redis = redis
        self._settings = settings

    def lock_key(self, category: str, *parts: str) -> str:
        safe = ":".join(parts)
        return f"lock:{category}:{safe}"

    def result_key(self, lock_key: str) -> str:
        return f"result:{lock_key}"

    async def acquire(self, *, key: str, ttl: timedelta | None = None) -> CoalesceLock | None:
        token = uuid.uuid4().hex
        ttl_seconds = int(
            (
                ttl or timedelta(seconds=self._settings.redis_lock_default_ttl_seconds)
            ).total_seconds()
        )
        ok = await self._redis.set(key, token, ex=ttl_seconds, nx=True)
        if ok:
            return CoalesceLock(key=key, token=token)
        return None

    async def release(self, lock: CoalesceLock) -> bool:
        result = await self._redis.eval(self._RELEASE_SCRIPT, 1, lock.key, lock.token)
        return int(result) == 1

    async def publish_result(self, lock_key: str, value: str, ttl: timedelta) -> None:
        await self._redis.set(self.result_key(lock_key), value, ex=int(ttl.total_seconds()))

    async def fetch_result(self, lock_key: str) -> str | None:
        value = await self._redis.get(self.result_key(lock_key))
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def wait_for_published(
        self,
        lock_key: str,
        *,
        max_wait: float | None = None,
        poll_interval: float = 0.05,
    ) -> str | None:
        """Poll for the winner's published result up to `max_wait`.

        Returns the published JSON payload or None. Callers must NEVER
        fall back to their own provider call on timeout — the lock is a
        quota/correctness boundary (M4.1 §5).
        """
        import asyncio

        settings_wait = self._settings.redis_lock_acquire_timeout_seconds
        wait = max_wait if max_wait is not None else settings_wait
        waited = 0.0
        while waited < wait:
            existing = await self.fetch_result(lock_key)
            if existing is not None:
                return existing
            await asyncio.sleep(poll_interval)
            waited += poll_interval
        return None


def _serialize(value: object) -> str:
    import json
    from dataclasses import asdict, is_dataclass

    if isinstance(value, str):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return json.dumps(asdict(value), default=str, ensure_ascii=False)
    return json.dumps(value, default=str, ensure_ascii=False)
