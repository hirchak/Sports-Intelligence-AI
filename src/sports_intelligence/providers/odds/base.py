from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OddsProvider(Protocol):
    """Provider-independent odds boundary (M4.1 §9).

    External calls always use PROVIDER identifiers: callers pass the
    configured sport_key plus a provider event id resolved through
    `resolve_event` (strict team+kickoff matching; ambiguity is an
    error, never guessed). Internal fixture UUIDs never reach URLs.
    """

    name: str

    async def resolve_event(
        self,
        *,
        sport_key: str,
        home_team: str,
        away_team: str,
        commence_time_utc: datetime,
        tolerance_seconds: int = 900,
    ) -> str:
        """Return the provider event id for exactly one matching event."""
        ...

    async def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult: ...

    def estimate_cost(self, *, markets: Sequence[str], regions: Sequence[str]) -> int: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class OddsSelectionPrice:
    """A single price inside one bookmaker / market / selection."""

    bookmaker: str
    market: str  # h2h_1x2 | double_chance | ou_15 | ou_25 | btts
    selection: str  # home | draw | away | over | under | yes | no | ...
    line: Decimal | None
    decimal_odds: Decimal


@dataclass(frozen=True)
class OddsEventRef:
    provider_event_id: str
    sport_key: str
    home_team: str | None = None
    away_team: str | None = None
    commence_time: datetime | None = None


@dataclass(frozen=True)
class OddsProviderResult:
    provider: str
    fixture_id: str  # provider event id (NOT an internal UUID)
    captured_at: str  # ISO timestamp from provider / capture moment
    prices: Sequence[OddsSelectionPrice] = field(default_factory=tuple)
    raw_payload_ref: str | None = None
    raw_payload: dict[str, Any] | None = None
    rate_headers: dict[str, str] = field(default_factory=dict)
