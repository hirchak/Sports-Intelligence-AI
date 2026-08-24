from __future__ import annotations

import pytest

from sports_intelligence.collectors.quota import (
    DegradationMode,
    Priority,
    QuotaDecisionKind,
    decide,
    effective_reserve,
    parse_quota_headers,
)


def _decide(
    *,
    daily_remaining: int | None,
    daily_limit: int = 100,
    minute_remaining: int | None = None,
    priority: Priority,
    reserve: int = 20,
    critical_pct: int = 10,
    conserve_pct: int = 25,
    estimated_cost: int = 1,
):
    return decide(
        daily_remaining=daily_remaining,
        daily_limit=daily_limit,
        minute_remaining=minute_remaining,
        minute_limit=10,
        reserve=reserve,
        critical_pct=critical_pct,
        conserve_pct=conserve_pct,
        priority=priority,
        estimated_cost=estimated_cost,
    )


@pytest.mark.parametrize(
    ("limit", "remaining"),
    [
        (100, 21),
        (500, 105),
        (7500, 1575),
    ],
)
def test_percentage_thresholds_scale_with_actual_limit(limit: int, remaining: int) -> None:
    """M4.1 §6: thresholds are PERCENTAGES of the actual provider limit.
    21% of any limit lands in the CONSERVE band."""
    decision = _decide(daily_remaining=remaining, daily_limit=limit, priority=Priority.P2)
    assert decision.mode is DegradationMode.CONSERVE
    assert decision.allowed is True


def test_critical_reachable_and_pauses_p2_preserves_p1() -> None:
    """Effective reserve is clamped into the CRITICAL band so CRITICAL
    stays reachable; CRITICAL pauses P2/P3 but preserves P0/P1."""
    # remaining 45 / limit 500 → 9% → CRITICAL.
    p2 = _decide(daily_remaining=45, daily_limit=500, priority=Priority.P2)
    assert p2.mode is DegradationMode.CRITICAL
    assert p2.allowed is False
    assert p2.kind is QuotaDecisionKind.DENIED_LOW_PRIORITY_PAUSED

    p1 = _decide(daily_remaining=45, daily_limit=500, priority=Priority.P1)
    assert p1.allowed is True

    p3 = _decide(daily_remaining=45, daily_limit=500, priority=Priority.P3)
    assert p3.allowed is False


def test_reserve_protects_only_p0() -> None:
    p0 = _decide(daily_remaining=8, priority=Priority.P0)
    assert p0.mode is DegradationMode.RESERVE_ONLY
    assert p0.allowed is True

    p2 = _decide(daily_remaining=8, priority=Priority.P2)
    assert p2.allowed is False
    assert p2.kind is QuotaDecisionKind.DENIED_RESERVE_ONLY


def test_conserve_pauses_p3() -> None:
    # remaining 20 / limit 100 → 20% → CONSERVE band (<=25).
    p3 = _decide(daily_remaining=20, priority=Priority.P3)
    assert p3.mode is DegradationMode.CONSERVE
    assert p3.allowed is False
    p2 = _decide(daily_remaining=20, priority=Priority.P2)
    assert p2.allowed is True


def test_estimated_cost_can_deny_daily_budget() -> None:
    decision = _decide(
        daily_remaining=3,
        priority=Priority.P0,
        estimated_cost=5,
    )
    assert decision.allowed is False
    assert decision.kind is QuotaDecisionKind.DENIED_NO_REMAINING


def test_minute_budget_exhausted_denies_p0() -> None:
    decision = _decide(
        daily_remaining=90,
        minute_remaining=0,
        priority=Priority.P0,
    )
    assert decision.allowed is False
    assert decision.kind is QuotaDecisionKind.DENIED_NO_REMAINING


def test_effective_reserve_clamps_to_critical_band() -> None:
    assert effective_reserve(daily_limit=100, reserve=20, critical_pct=10) == 10
    assert effective_reserve(daily_limit=500, reserve=20, critical_pct=10) == 20
    assert effective_reserve(daily_limit=7500, reserve=20, critical_pct=10) == 20


def test_parse_headers_api_football_daily_and_minute() -> None:
    obs = parse_quota_headers(
        "api_football",
        {
            "x-ratelimit-requests-limit": "100",
            "x-ratelimit-requests-remaining": "42",
            "x-ratelimit-limit": "300",
            "x-ratelimit-remaining": "297",
        },
    )
    assert obs.daily_limit == 100
    assert obs.daily_remaining == 42
    assert obs.minute_limit == 300
    assert obs.minute_remaining == 297
    assert obs.last_call_cost is None


def test_parse_headers_the_odds_api_uses_cost_not_minute() -> None:
    """M4.1 §7: x-requests-last is the COST of the last call, never a
    per-minute budget."""
    obs = parse_quota_headers(
        "theoddsapi",
        {
            "x-requests-remaining": "492",
            "x-requests-used": "8",
            "x-requests-last": "5",
        },
    )
    assert obs.daily_remaining == 492
    assert obs.last_call_cost == 5
    assert obs.minute_remaining is None
    assert obs.daily_limit is None


def test_parse_headers_empty() -> None:
    obs = parse_quota_headers("api_football", {})
    assert obs.daily_remaining is None
    assert obs.daily_limit is None
