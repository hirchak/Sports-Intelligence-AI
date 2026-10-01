"""Context subsystem exceptions."""

from __future__ import annotations

import uuid
from datetime import datetime


class HistoricalFixtureMetadataUnavailable(Exception):
    """Raised when no FixtureMetadataSnapshot exists with captured_at <= as_of.

    When this exception is raised the builder must NOT persist
    FeatureSnapshot, DataQualityReport, or MatchContext — the
    fixture's historical identity is unknown at the requested
    point in time.
    """

    def __init__(self, fixture_id: uuid.UUID, as_of: datetime) -> None:
        self.fixture_id = fixture_id
        self.as_of = as_of
        super().__init__(
            f"No fixture metadata snapshot exists for fixture {fixture_id} "
            f"at or before {as_of.isoformat()}"
        )
