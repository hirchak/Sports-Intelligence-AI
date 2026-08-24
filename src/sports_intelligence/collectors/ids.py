"""Internal UUID → provider external ID resolution (M4.1 §2).

Internal UUIDs are NEVER sent to external APIs. Collectors resolve
provider-facing ids through `provider_entity_ids` populated by M2
discovery.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.db.models import ProviderEntityId


class ExternalIdResolutionError(RuntimeError):
    """The internal entity has no external id for this provider."""


async def resolve_external_id(
    session: AsyncSession,
    *,
    provider: str,
    entity_type: str,
    internal_id: uuid.UUID | str,
) -> int:
    stmt = (
        select(ProviderEntityId.external_id)
        .where(
            ProviderEntityId.provider == provider,
            ProviderEntityId.entity_type == entity_type,
            ProviderEntityId.internal_entity_id == internal_id,
        )
        .order_by(ProviderEntityId.last_seen_at.desc())
        .limit(1)
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    if value is None:
        raise ExternalIdResolutionError(
            f"no {provider} {entity_type} mapping for internal id {internal_id}"
        )
    return int(value)


async def upsert_external_id(
    session: AsyncSession,
    *,
    provider: str,
    entity_type: str,
    external_id: str | int,
    internal_id: uuid.UUID | str,
) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(ProviderEntityId)
        .values(
            provider=provider,
            entity_type=entity_type,
            external_id=str(external_id),
            internal_entity_id=internal_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ProviderEntityId.provider,
                ProviderEntityId.entity_type,
                ProviderEntityId.external_id,
            ]
        )
    )
    await session.execute(stmt)
