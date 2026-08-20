from __future__ import annotations

import uuid
from datetime import UTC

from sports_intelligence.core.ids import new_id
from sports_intelligence.core.time import utc_now


def test_utc_now_is_timezone_aware_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(now)


def test_new_id_is_valid_uuid4_string() -> None:
    value = new_id()
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_new_id_is_unique() -> None:
    assert new_id() != new_id()
