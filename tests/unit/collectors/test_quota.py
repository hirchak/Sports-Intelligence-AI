from __future__ import annotations

import pytest

from sports_intelligence.collectors.quota import (
    DegradationMode,
    Priority,
    QuotaDecisionKind,
    decide,
)

# Pure-function decision matrix. Deterministic, no DB.


@pytest.mark.parametrize(
    ("daily_remaining", "minute_remaining", "priority", "expected_allowed", "expected_mode"),
    [
        # NORMAL: P0..P3 all allowed.
        (90, 5, Priority.P0, True, DegradationMode.NORMAL),
        (90, 5, Priority.P3, True, DegradationMode.NORMAL),
        # CONSERVE: P3 paused; P0..P2 allowed.
        (15, 5, Priority.P3, False, DegradationMode.CONSERVE),
        (15, 5, Priority.P2, True, DegradationMode.CONSERVE),
        (15, 5, Priority.P1, True, DegradationMode.CONSERVE),
        (15, 5, Priority.P0, True, DegradationMode.CONSERVE),
        # CRITICAL: P3 paused; P0..P2 allowed. (reserve=2 keeps 5 daily
        # above the reserve floor and inside the CRITICAL band.)
        (5, 5, Priority.P3, False, DegradationMode.CRITICAL),
        (5, 5, Priority.P2, True, DegradationMode.CRITICAL),
        # RESERVE_ONLY: only P0.
        (1, 5, Priority.P3, False, DegradationMode.RESERVE_ONLY),
        (1, 5, Priority.P2, False, DegradationMode.RESERVE_ONLY),
        (1, 5, Priority.P1, False, DegradationMode.RESERVE_ONLY),
        (1, 5, Priority.P0, True, DegradationMode.RESERVE_ONLY),
        # Minute-budget exhausted: even P0 denied.
        (90, 0, Priority.P0, False, DegradationMode.NORMAL),
    ],
)
def test_decide_matrix(
    daily_remaining: int | None,
    minute_remaining: int | None,
    priority: Priority,
    expected_allowed: bool,
    expected_mode: DegradationMode,
) -> None:
    decision = decide(
        daily_remaining=daily_remaining,
        daily_limit=100,
        minute_remaining=minute_remaining,
        minute_limit=10,
        reserve=2,
        thresholds=(10, 25, 50),
        priority=priority,
    )
    assert decision.allowed is expected_allowed
    assert decision.mode is expected_mode
    assert decision.remaining_daily == daily_remaining
    assert decision.remaining_minute == minute_remaining


def test_decide_denies_p3_in_conserve_with_reserve_reason() -> None:
    decision = decide(
        daily_remaining=15,
        daily_limit=100,
        minute_remaining=5,
        minute_limit=10,
        reserve=5,
        thresholds=(10, 25, 50),
        priority=Priority.P3,
    )
    assert decision.kind is QuotaDecisionKind.DENIED_LOW_PRIORITY_PAUSED
    assert decision.reason == "conserve_p3_paused"


def test_decide_denies_reserve_only_with_reserve_only_reason() -> None:
    decision = decide(
        daily_remaining=1,
        daily_limit=100,
        minute_remaining=5,
        minute_limit=10,
        reserve=5,
        thresholds=(10, 25, 50),
        priority=Priority.P2,
    )
    assert decision.kind is QuotaDecisionKind.DENIED_RESERVE_ONLY
    assert decision.reason == "reserve_only"


def test_decide_no_remaining_denies_p0() -> None:
    decision = decide(
        daily_remaining=90,
        daily_limit=100,
        minute_remaining=0,
        minute_limit=10,
        reserve=5,
        thresholds=(10, 25, 50),
        priority=Priority.P0,
    )
    assert decision.kind is QuotaDecisionKind.DENIED_NO_REMAINING


def test_parse_provider_headers_api_football() -> None:
    from sports_intelligence.collectors.quota import parse_provider_headers

    parsed = parse_provider_headers(
        {
            "x-ratelimit-requests-remaining": "42",
            "x-ratelimit-requests-limit": "100",
        }
    )
    assert parsed.daily_remaining == 42
    assert parsed.daily_limit == 100


def test_parse_provider_headers_the_odds_api() -> None:
    from sports_intelligence.collectors.quota import parse_provider_headers

    parsed = parse_provider_headers({"x-requests-remaining": "200", "x-requests-limit": "500"})
    assert parsed.daily_remaining == 200
    assert parsed.daily_limit == 500


def test_parse_provider_headers_empty() -> None:
    from sports_intelligence.collectors.quota import parse_provider_headers

    parsed = parse_provider_headers({})
    assert parsed.daily_remaining is None
    assert parsed.daily_limit is None
