from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeVar

from redis.asyncio import Redis

from sports_intelligence.core.config import Settings

T = TypeVar("T")


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

    async def wait_or_use(
        self,
        *,
        key: str,
        fetch_fresh: Callable[[], Awaitable[T]],
        ttl: timedelta | None = None,
        max_wait: timedelta | None = None,
    ) -> T:
        """Run `fetch_fresh` exactly once for equivalent callers.

        Winner: acquires lock, runs fetch, releases lock, publishes
        result for waiters, returns result.
        Waiters: poll the companion result key up to `max_wait`; on
        timeout, falls back to acquiring the lock and fetching.
        """
        result_ttl = ttl or timedelta(seconds=self._settings.redis_lock_default_ttl_seconds)
        lock = await self.acquire(key=key, ttl=result_ttl)
        if lock is not None:
            try:
                result = await fetch_fresh()
                with suppress(Exception):  # best-effort result publication
                    await self.publish_result(key, _serialize(result), result_ttl)
                return result
            finally:
                await self.release(lock)

        # Wait for the winner to publish its result.
        wait = max_wait or timedelta(seconds=self._settings.redis_lock_acquire_timeout_seconds)
        waited = 0.0
        interval = 0.05
        while waited < wait.total_seconds():
            existing = await self.fetch_result(key)
            if existing is not None:
                return _deserialize(existing)  # type: ignore[return-value]
            import asyncio

            await asyncio.sleep(interval)
            waited += interval

        # Fall back to taking the lock and fetching ourselves.
        lock = await self.acquire(key=key, ttl=result_ttl)
        if lock is None:
            # Still contended — fetch anyway (best effort, the lock
            # is purely an optimisation, never a correctness barrier).
            return await fetch_fresh()
        try:
            return await fetch_fresh()
        finally:
            await self.release(lock)


def _serialize(value: object) -> str:
    import json
    from dataclasses import asdict, is_dataclass

    if isinstance(value, str):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return json.dumps(asdict(value), default=str, ensure_ascii=False)
    return json.dumps(value, default=str, ensure_ascii=False)


def _deserialize(value: str) -> object:
    import json

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value
