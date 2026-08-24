from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class OddsProvider(Protocol):
    name: str

    async def fetch_odds(
        self,
        *,
        fixture_id: str,
        markets: Sequence[str],
        regions: Sequence[str],
    ) -> OddsProviderResult: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class OddsSelectionPrice:
    """A single price inside one bookmaker / market / selection."""

    bookmaker: str
    market: str  # h2h_1x2 | double_chance | ou_1_5 | ou_2_5 | btts
    selection: str  # home | draw | away | over | under | yes | no | home_or_draw | ...
    line: Decimal | None
    decimal_odds: Decimal


@dataclass(frozen=True)
class OddsProviderResult:
    provider: str
    fixture_id: str
    captured_at: str  # ISO timestamp from provider / capture moment
    prices: Sequence[OddsSelectionPrice] = field(default_factory=tuple)
    raw_payload_ref: str | None = None
