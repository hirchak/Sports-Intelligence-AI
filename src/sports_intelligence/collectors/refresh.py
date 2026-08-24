"""Deterministic collector refresh-opportunity identity (M4.2 §1/§2).

A collector JOB must encode WHICH refresh opportunity it represents.
Repeated scans inside the same opportunity dedupe to one job; a later
legitimate opportunity (new T-window for lineups, new time bucket for
TTL categories) creates a NEW job.

Rules:

- lineups: explicit T-window identity (`t120` / `t60` / `t20`) derived
  from kickoff vs now — a NOT_YET_PUBLISHED snapshot at T-120 permits a
  T-60 refresh; the 24h lineup TTL never overrides window logic;
- every other category: a deterministic freshness time bucket derived
  from the category TTL (bucket ≈ TTL/2, min 5 min) so any scan after a
  snapshot expires falls in a strictly later bucket.
"""

from __future__ import annotations

from datetime import UTC, datetime

_MIN_BUCKET_SECONDS = 300


def active_lineup_window_id(
    *,
    kickoff_at: datetime,
    now: datetime,
    windows_minutes: list[int],
) -> str | None:
    """Return the T-window the fixture is currently inside
    (`t120`/`t60`/`t20`), or None when outside every window (or started).
    """
    kickoff = _aware(kickoff_at)
    moment = _aware(now)
    minutes_to_kickoff = (kickoff - moment).total_seconds() / 60.0
    if minutes_to_kickoff <= 0:
        return None
    # Smallest window the fixture is inside (most restrictive):
    # T-50 → t60, never t120.
    windows = sorted(w for w in windows_minutes if w > 0)
    for window in windows:
        if minutes_to_kickoff <= window:
            return f"t{window}"
    return None


def refresh_opportunity_suffix(
    *,
    collector_name: str,
    kickoff_at: datetime | None,
    now: datetime,
    windows_minutes: list[int],
    ttl_seconds: int,
) -> str:
    """Deterministic suffix for a collector job's idempotency key.

    - `lineups` → the active T-window id (`t120` / `t60` / `t20`) or
      `no_window`;
    - everything else → `b<epoch bucket>` where the bucket is tied to
      the category TTL so expired snapshots always open a new bucket.
    """
    if collector_name == "lineups":
        if kickoff_at is None:
            return "no_window"
        window = active_lineup_window_id(
            kickoff_at=kickoff_at, now=now, windows_minutes=windows_minutes
        )
        return window or "no_window"
    bucket_seconds = max(int(ttl_seconds) // 2, _MIN_BUCKET_SECONDS)
    bucket = int(_aware(now).timestamp() // bucket_seconds)
    return f"b{bucket}"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
