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


def test_ttl_opportunity_stable_while_fresh_changes_when_stale() -> None:
    """M4.3 §4: opportunity = due generation (captured + TTL while
    fresh; now once stale) — never an unrelated global bucket."""
    ttl_seconds = 1800  # 30 min odds PREMATCH TTL
    captured = KICKOFF - timedelta(minutes=40)
    # Fresh snapshot → due = captured + TTL, stable across scans.
    suffix_a = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=captured + timedelta(minutes=5),
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
        latest_captured_at=captured,
    )
    suffix_b = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=captured + timedelta(minutes=20),
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
        latest_captured_at=captured,
    )
    assert suffix_a == suffix_b == f"due:{int((captured + timedelta(seconds=1800)).timestamp())}"


def test_stale_inside_old_bucket_opens_new_opportunity() -> None:
    """Counterexample regression (M4.3 §4): a job created while the
    snapshot is still fresh; time advances just past the TTL but inside
    the old global bucket — the scanner must create a NEW refresh
    opportunity, not be suppressed by an unrelated bucket boundary."""
    ttl_seconds = 1800
    captured = KICKOFF - timedelta(minutes=40)  # captured at T-40
    # Scan inside the same old bucket but BEFORE stale → same due.
    fresh_suffix = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=captured + timedelta(minutes=25),  # captured+25min < captured+30min TTL
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
        latest_captured_at=captured,
    )
    # Snapshot is stale now (captured+31min > TTL); still INSIDE the old
    # global bucket boundary → due must advance to now.
    stale_suffix = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=KICKOFF,
        now=captured + timedelta(minutes=31),
        windows_minutes=WINDOWS,
        ttl_seconds=ttl_seconds,
        latest_captured_at=captured,
    )
    assert fresh_suffix != stale_suffix
    assert stale_suffix == f"due:{int((captured + timedelta(minutes=31)).timestamp())}"


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
