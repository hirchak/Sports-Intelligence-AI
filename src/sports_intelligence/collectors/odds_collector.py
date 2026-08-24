from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    SnapshotRef,
    register,
)
from sports_intelligence.collectors.odds_math import (
    OddsPriceError,
    derive_market_view,
    quantize,
)
from sports_intelligence.core.phases import FreshnessCategory, Priority
from sports_intelligence.db.models import (
    OddsPrice,
    OddsSnapshotSet,
)
from sports_intelligence.providers.odds.base import OddsProvider


class OddsCollector:
    name = "odds"
    category = FreshnessCategory.ODDS
    priority = Priority.P1

    def __init__(self) -> None:
        pass

    def lock_key(self, *, fixture_id: object, **_: Any) -> str:
        return f"odds:{fixture_id}"

    def _require_odds_provider(self, ctx: CollectorContext) -> OddsProvider:
        provider = ctx.provider
        if not isinstance(provider, OddsProvider):
            raise RuntimeError("odds collector requires an OddsProvider context")
        return provider

    async def latest_captured_at(
        self, session: AsyncSession, *, fixture_id: object, **_: Any
    ) -> datetime | None:
        stmt = (
            select(OddsSnapshotSet.captured_at)
            .where(OddsSnapshotSet.fixture_id == fixture_id)
            .order_by(OddsSnapshotSet.captured_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def fetch(
        self,
        ctx: CollectorContext,
        *,
        fixture_id: object,
        **_: Any,
    ) -> CollectorResult:
        provider = self._require_odds_provider(ctx)
        ctx_settings = ctx.settings
        result = await provider.fetch_odds(
            fixture_id=str(fixture_id),
            markets=ctx_settings.odds_provider_markets,
            regions=ctx_settings.odds_provider_regions,
        )
        # Decimal values are stringified: the framework publishes the
        # winner's result via Redis as JSON, so the waiter path must be
        # JSON-safe. persist() re-parses strings back to Decimal.
        return CollectorResult(
            raw_payload=None,
            normalized={
                "fixture_id": result.fixture_id,
                "captured_at": result.captured_at,
                "prices": [
                    {
                        "bookmaker": p.bookmaker,
                        "market": p.market,
                        "selection": p.selection,
                        "line": str(p.line) if p.line is not None else None,
                        "decimal_odds": str(p.decimal_odds),
                    }
                    for p in result.prices
                ],
            },
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        fixture_id: object,
        **_: Any,
    ) -> SnapshotRef:
        import uuid as _uuid
        from decimal import Decimal, InvalidOperation

        markets: Sequence[str] = ctx.settings.odds_provider_markets

        fixture_uuid = _uuid.UUID(str(fixture_id))
        from sports_intelligence.db.models import Fixture as FixtureModel

        raw_prices = result.normalized.get("prices", [])

        snapshot_set = OddsSnapshotSet(
            provider=ctx.provider_name(),
            fixture_id=fixture_uuid,
            captured_at=captured_at,
            market_whitelist_jsonb=list(markets),
        )
        prices_rows: list[dict[str, object]] = []
        for row in raw_prices:
            try:
                decimal_odds = Decimal(str(row["decimal_odds"]))
            except (KeyError, InvalidOperation, ValueError) as exc:
                raise ValueError(f"invalid decimal odds in odds payload: {exc}") from exc
            line_str = row.get("line")
            line = None
            if line_str is not None:
                try:
                    line = Decimal(str(line_str))
                except (InvalidOperation, ValueError):
                    line = None
            prices_rows.append(
                {
                    "bookmaker": str(row["bookmaker"]),
                    "market": str(row["market"]),
                    "selection": str(row["selection"]),
                    "line": line,
                    "decimal_odds": decimal_odds,
                }
            )

        grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in prices_rows:
            key = (str(row["bookmaker"]), str(row["market"]))
            grouped.setdefault(key, []).append(row)

        async with ctx.session_factory() as session:
            exists = await session.get(FixtureModel, fixture_uuid)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for odds persist")

            session.add(snapshot_set)
            await session.flush()  # populate snapshot_set.id

            for (bookmaker, market), rows in grouped.items():
                selections = tuple(str(r["selection"]) for r in rows)
                decimal_prices = tuple(Decimal(str(r["decimal_odds"])) for r in rows)
                try:
                    view = derive_market_view(
                        bookmaker=bookmaker,
                        market=market,
                        selections=selections,
                        decimal_prices=decimal_prices,
                    )
                except OddsPriceError:
                    view = None
                nv_by_selection: dict[str, Decimal | None] = {}
                if view is not None:
                    nv_by_selection = dict(
                        zip(selections, view.no_vig or [None] * len(selections), strict=False)
                    )

                for row in rows:
                    nv = nv_by_selection.get(str(row["selection"]))
                    session.add(
                        OddsPrice(
                            snapshot_set_id=snapshot_set.id,
                            bookmaker=bookmaker,
                            market=market,
                            selection=str(row["selection"]),
                            line=row["line"],
                            decimal_odds=quantize(Decimal(str(row["decimal_odds"]))),
                            implied_probability=quantize(
                                Decimal("1") / Decimal(str(row["decimal_odds"]))
                            ),
                            no_vig_probability=quantize(nv) if nv is not None else None,
                        )
                    )
            await session.commit()
        return SnapshotRef(
            table="odds_snapshot_sets", snapshot_id=snapshot_set.id, captured_at=captured_at
        )


register(OddsCollector())
