from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    SnapshotRef,
    register,
)
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.core.phases import FreshnessCategory, Priority
from sports_intelligence.db.models import (
    Fixture,
    League,
    OddsEventMapping,
    OddsPrice,
    OddsSnapshotSet,
    Team,
)
from sports_intelligence.providers.errors import ProviderMappingError
from sports_intelligence.providers.odds.base import OddsProvider


class OddsCollector:
    name = "odds"
    category = FreshnessCategory.ODDS
    priority = Priority.P1

    def lock_key(self, *, fixture_id: object, **_: Any) -> str:
        return f"odds:{fixture_id}"

    def _require_odds_provider(self, ctx: CollectorContext) -> OddsProvider:
        provider = ctx.provider
        if not isinstance(provider, OddsProvider):
            raise RuntimeError("odds collector requires an OddsProvider context")
        return provider

    async def latest_snapshot(
        self, session: AsyncSession, *, fixture_id: object, **_: Any
    ) -> tuple[datetime | None, _uuid.UUID | None]:
        stmt = (
            select(OddsSnapshotSet.captured_at, OddsSnapshotSet.id)
            .where(OddsSnapshotSet.fixture_id == fixture_id)
            .order_by(OddsSnapshotSet.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def _sport_key_for_league(
        self, session: AsyncSession, ctx: CollectorContext, league_id: _uuid.UUID
    ) -> str:
        slug = (
            await session.execute(select(League.slug).where(League.id == league_id))
        ).scalar_one_or_none()
        if slug is None:
            raise ProviderMappingError(f"league {league_id} not found for odds mapping")
        config = load_league_config(ctx.settings.leagues_config_path)
        for entry in config.leagues:
            if entry.slug == str(slug):
                if entry.odds_sport_key:
                    return entry.odds_sport_key
                break
        raise ProviderMappingError(
            f"no odds_sport_key configured for league {slug!r}; refusing to guess"
        )

    async def _resolve_or_get_event_id(
        self,
        session: AsyncSession,
        ctx: CollectorContext,
        *,
        fixture_id: _uuid.UUID,
        sport_key: str,
    ) -> str:
        provider_name = self._require_odds_provider(ctx).name
        stmt = select(OddsEventMapping.provider_event_id).where(
            OddsEventMapping.provider == provider_name,
            OddsEventMapping.fixture_id == fixture_id,
            OddsEventMapping.sport_key == sport_key,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise LookupError(f"fixture {fixture_id} not found for odds collection")
        # M4.2 §7: load home and away EXPLICITLY by their ids — never an
        # unordered SQL IN whose row order is undefined.
        home_name = (
            await session.execute(select(Team.name).where(Team.id == fixture.home_team_id))
        ).scalar_one_or_none()
        away_name = (
            await session.execute(select(Team.name).where(Team.id == fixture.away_team_id))
        ).scalar_one_or_none()
        if not home_name or not away_name:
            raise ProviderMappingError(
                f"fixture {fixture_id} lacks team names required for event resolution"
            )

        provider = self._require_odds_provider(ctx)
        kickoff = fixture.kickoff_at
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        event_id = await provider.resolve_event(
            sport_key=sport_key,
            home_team=home_name,
            away_team=away_name,
            commence_time_utc=kickoff,
        )
        mapping = OddsEventMapping(
            provider=provider_name,
            sport_key=sport_key,
            provider_event_id=event_id,
            fixture_id=fixture_id,
            home_team_name=home_name,
            away_team_name=away_name,
            commence_time=kickoff,
            mapped_at=datetime.now(UTC),
        )
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt_ins = (
            pg_insert(OddsEventMapping)
            .values(
                provider=mapping.provider,
                sport_key=mapping.sport_key,
                provider_event_id=mapping.provider_event_id,
                fixture_id=mapping.fixture_id,
                home_team_name=mapping.home_team_name,
                away_team_name=mapping.away_team_name,
                commence_time=mapping.commence_time,
                mapped_at=mapping.mapped_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    OddsEventMapping.provider,
                    OddsEventMapping.provider_event_id,
                ]
            )
        )
        await session.execute(stmt_ins)
        await session.commit()
        return event_id

    async def fetch(
        self,
        ctx: CollectorContext,
        *,
        fixture_id: object,
        **_: Any,
    ) -> CollectorResult:
        provider = self._require_odds_provider(ctx)
        fixture_uuid = _uuid.UUID(str(fixture_id))
        # M4.3 §2: the provider owns the translation from the configured
        # (internal) market set to the ACTUAL provider keys sent over
        # HTTP (e.g. totals + alternate_totals for exact O/U lines).
        request_markets: Sequence[str] = provider.request_markets(
            ctx.settings.odds_provider_markets
        )
        regions: Sequence[str] = ctx.settings.odds_provider_regions

        async with ctx.session_factory() as session:
            league_id = (
                await session.execute(select(Fixture.league_id).where(Fixture.id == fixture_uuid))
            ).scalar_one()
            sport_key = await self._sport_key_for_league(session, ctx, league_id)
            event_id = await self._resolve_or_get_event_id(
                session, ctx, fixture_id=fixture_uuid, sport_key=sport_key
            )

        result = await provider.fetch_event_odds(
            sport_key=sport_key,
            event_id=event_id,
            markets=request_markets,
            regions=regions,
        )
        # Decimal values stringified: framework publishes results via
        # Redis JSON; persist() re-parses strings back to Decimal.
        return CollectorResult(
            raw_payload=result.raw_payload or {"prices": []},
            normalized={
                "provider_event_id": result.fixture_id,
                "sport_key": sport_key,
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
            rate_headers=dict(result.rate_headers),
            retrieved_at=None,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: _uuid.UUID | None,
        fixture_id: object,
        **_: Any,
    ) -> tuple[SnapshotRef, ...]:
        markets: Sequence[str] = ctx.settings.odds_provider_markets

        fixture_uuid = _uuid.UUID(str(fixture_id))
        raw_prices = result.normalized.get("prices", [])

        snapshot_set = OddsSnapshotSet(
            provider=ctx.provider_name(),
            fixture_id=fixture_uuid,
            captured_at=captured_at,
            market_whitelist_jsonb=list(markets),
            payload_id=payload_id,
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
            exists = await session.get(Fixture, fixture_uuid)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for odds persist")

            session.add(snapshot_set)
            await session.flush()

            for (bookmaker, market), rows in grouped.items():
                selections = tuple(str(r["selection"]) for r in rows)
                decimal_prices = tuple(Decimal(str(r["decimal_odds"])) for r in rows)
                view = derive_market_view_safe(bookmaker, market, selections, decimal_prices)
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
                            no_vig_probability=(quantize(nv) if nv is not None else None),
                        )
                    )
            await session.commit()
        return (
            SnapshotRef(
                table="odds_snapshot_sets",
                snapshot_id=snapshot_set.id,
                captured_at=captured_at,
            ),
        )


def derive_market_view_safe(
    bookmaker: str, market: str, selections: Sequence[str], prices: tuple[Decimal, ...]
) -> Any:
    """No-vig normalization ONLY on a COMPLETE expected selection set
    (M4.2 §6). An incomplete 1X2 / double-chance / two-sided O-U / BTTS
    market is never normalized merely because its implied probabilities
    happen to sum above 1."""
    from sports_intelligence.collectors.odds_math import (
        OddsPriceError,
        derive_market_view,
    )

    expected: dict[str, frozenset[str]] = {
        "h2h_1x2": frozenset({"home", "draw", "away"}),
        "double_chance": frozenset({"home_or_draw", "draw_or_away", "home_or_away"}),
        "ou_15": frozenset({"over", "under"}),
        "ou_25": frozenset({"over", "under"}),
        "btts": frozenset({"yes", "no"}),
    }
    required = expected.get(market)
    if required is None:
        # Unknown canonical market: derive nothing.
        return None
    if set(selections) != required:
        return None
    try:
        return derive_market_view(
            bookmaker=bookmaker,
            market=market,
            selections=selections,
            decimal_prices=prices,
        )
    except OddsPriceError:
        return None


def quantize(value: Decimal) -> Decimal:
    from sports_intelligence.collectors.odds_math import quantize as q

    return q(value)


register(OddsCollector())
