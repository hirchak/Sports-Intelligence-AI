from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest

from sports_intelligence.core.time import local_today, utc_window_for_local_day

WARSAW = "Europe/Warsaw"


def test_local_today_uses_app_timezone_near_utc_midnight() -> None:
    moment = datetime(2026, 8, 20, 23, 30, tzinfo=UTC)
    assert local_today(moment, WARSAW) == date(2026, 8, 21)


def test_local_today_within_utc_day_is_same_local_day() -> None:
    moment = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    assert local_today(moment, WARSAW) == date(2026, 8, 21)


def test_summer_day_window_has_24_hours() -> None:
    start, end = utc_window_for_local_day(date(2026, 8, 21), WARSAW)
    assert start == datetime(2026, 8, 20, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=24)


def test_dst_transition_day_window_has_25_hours() -> None:
    start, end = utc_window_for_local_day(date(2026, 10, 25), WARSAW)
    assert start == datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=25)


def test_unknown_timezone_raises() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        utc_window_for_local_day(date(2026, 8, 21), "Not/AZone")
