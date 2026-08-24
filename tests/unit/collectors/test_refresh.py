"""M4.2 §1/§2 — refresh-opportunity identity + T-window policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sports_intelligence.collectors.refresh import (
    active_lineup_window_id,
    refresh_opportunity_suffix,
)
from sports_intelligence.collectors.sports_collectors import lineup_poll_due

WINDOWS = [120, 60, 20]
KICKOFF = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)


def test_active_window_id_outside_all_windows() -> None:
    now = KICKOFF - timedelta(minutes=300)
    assert active_lineup_window_id(kickoff_at=KICKOFF, now=now, windows_minutes=WINDOWS) is None


def test_active_window_id_inside_t120() -> None:
    now = KICKOFF - timedelta(minutes=110)
    assert active_lineup_window_id(kickoff_at=KICKOFF, now=now, windows_minutes=WINDOWS) == "t120"


def test_active_window_id_inside_t60() -> None:
    now = KICKOFF - timedelta(minutes=50)
    assert active_lineup_window_id(kickoff_at=KICKOFF, now=now, windows_minutes=WINDOWS) == "t60"


def test_active_window_id_inside_t20() -> None:
    now = KICKOFF - timedelta(minutes=10)
    assert active_lineup_window_id(kickoff_at=KICKOFF, now=now, windows_minutes=WINDOWS) == "t20"


def test_active_window_id_started_is_none() -> None:
    now = KICKOFF + timedelta(minutes=5)
    assert active_lineup_window_id(kickoff_at=KICKOFF, now=now, windows_minutes=WINDOWS) is None


def test_lineup_opportunity_changes_per_window() -> None:
    """Distinct T-window identities: t120 ≠ t60 ≠ t20 — a later window
    ALWAYS opens a new refresh opportunity."""
    t120 = refresh_opportunity_suffix(
        collector_name="lineups",
        kickoff_at=KICKOFF,
        now=KICKOFF - timedelta(minutes=110),
        windows_minutes=WINDOWS,
        ttl_seconds=24 * 3600,
    )
    t60 = refresh_opportunity_suffix(
        collector_name="lineups",
        kickoff_at=KICKOFF,
        now=KICKOFF - timedelta(minutes=50),
        windows_minutes=WINDOWS,
        ttl_seconds=24 * 3600,
    )
    t20 = refresh_opportunity_suffix(
        collector_name="lineups",
        kickoff_at=KICKOFF,
        now=KICKOFF - timedelta(minutes=10),
        windows_minutes=WINDOWS,
        ttl_seconds=24 * 3600,
    )
    assert t120 == "t120"
    assert t60 == "t60"
    assert t20 == "t20"
    assert len({t120, t60, t20}) == 3


def test_ttl_bucket_opportunity_advances_after_ttl() -> None:
    """A TTL category: scans inside the same bucket dedupe; a scan after
    the TTL window lands in a strictly later bucket → new job."""
    ttl_seconds = 1800  # 30 min odds PREMATCH TTL → bucket 900s
    base = KICKOFF - timedelta(minutes=40)
    bucket_a = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=base,
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
    )
    same_bucket = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=base + timedelta(minutes=5),
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
    )
    later_bucket = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=base + timedelta(minutes=31),  # beyond the 30-min TTL
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
    )
    assert bucket_a == same_bucket
    assert bucket_a != later_bucket


def test_lineup_poll_due_t120_unconfirmed_permits_t60() -> None:
    captured_t110 = KICKOFF - timedelta(minutes=110)
    now_t50 = KICKOFF - timedelta(minutes=50)
    assert (
        lineup_poll_due(
            kickoff_at=KICKOFF,
            now=now_t50,
            windows_minutes=WINDOWS,
            latest_state="NOT_YET_PUBLISHED",
            latest_captured_at=captured_t110,
        )
        is True
    )


def test_lineup_poll_due_confirmed_stops_t20() -> None:
    captured_t60 = KICKOFF - timedelta(minutes=60)
    now_t20 = KICKOFF - timedelta(minutes=20)
    assert (
        lineup_poll_due(
            kickoff_at=KICKOFF,
            now=now_t20,
            windows_minutes=WINDOWS,
            latest_state="CONFIRMED",
            latest_captured_at=captured_t60,
        )
        is False
    )


def test_lineup_poll_due_started_never_polled() -> None:
    now = KICKOFF + timedelta(minutes=10)
    assert (
        lineup_poll_due(
            kickoff_at=KICKOFF,
            now=now,
            windows_minutes=WINDOWS,
            latest_state="NOT_YET_PUBLISHED",
            latest_captured_at=None,
        )
        is False
    )
