from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    SnapshotRef,
    register,
)
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.phases import (
    ClaimType,
    ForecastPhase,
    FreshnessCategory,
    Priority,
    ResearchState,
)
from sports_intelligence.db.models import (
    Fixture,
    ResearchClaim,
    ResearchDocument,
    ResearchRun,
    Team,
)
from sports_intelligence.providers.search.base import (
    SearchProvider,
    SearchResultItem,
)
from sports_intelligence.research.conflict import detect_conflicts
from sports_intelligence.research.dedup import (
    content_sha256,
    deduplicate_search_results,
    normalize_url,
)
from sports_intelligence.research.extractor import (
    ClaimExtractor,
    RuleBasedClaimExtractor,
)
from sports_intelligence.research.models import ExtractedClaimDTO
from sports_intelligence.research.query_builder import build_research_queries

logger = get_logger(__name__)


class ResearchCollector:
    name = "research"
    category = FreshnessCategory.RESEARCH
    priority = Priority.P3

    def __init__(self, extractor: ClaimExtractor | None = None) -> None:
        self.extractor = extractor or RuleBasedClaimExtractor()

    def lock_key(self, *, fixture_id: object, **_: Any) -> str:
        return f"research:{fixture_id}"

    def cost_estimate(self, **_: Any) -> int:
        return 6

    def _require_search_provider(self, ctx: CollectorContext) -> SearchProvider:
        provider = ctx.provider
        if not isinstance(provider, SearchProvider):
            raise RuntimeError(
                f"research collector requires a SearchProvider context, got {type(provider)}"
            )
        return provider

    async def latest_snapshot(
        self, session: AsyncSession, *, fixture_id: object, **_: Any
    ) -> tuple[datetime | None, _uuid.UUID | None]:
        fid = _uuid.UUID(str(fixture_id))
        stmt = (
            select(ResearchRun.captured_at, ResearchRun.id)
            .where(ResearchRun.fixture_id == fid)
            .order_by(ResearchRun.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self,
        ctx: CollectorContext,
        *,
        fixture_id: object,
        phase: str = ForecastPhase.MORNING.value,
        **_: Any,
    ) -> CollectorResult:
        fid = _uuid.UUID(str(fixture_id))
        if not ctx.settings.research_capability_enabled or not isinstance(
            ctx.provider, SearchProvider
        ):
            return CollectorResult(
                raw_payload={"status": "disabled"},
                normalized={
                    "fixture_id": str(fid),
                    "phase": phase,
                    "status": ResearchState.NO_USEFUL_RESULTS.value,
                    "provider": "disabled",
                    "queries": [],
                    "queries_count": 0,
                    "documents_count": 0,
                    "claims_count": 0,
                    "conflicts_count": 0,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "documents": [],
                },
            )
        provider = ctx.provider

        # 1. Resolve fixture context
        async with ctx.session_factory() as session:
            HomeTeam = aliased(Team, name="home_team")
            AwayTeam = aliased(Team, name="away_team")
            stmt = (
                select(Fixture, HomeTeam, AwayTeam)
                .join(HomeTeam, HomeTeam.id == Fixture.home_team_id)
                .join(AwayTeam, AwayTeam.id == Fixture.away_team_id)
                .where(Fixture.id == fid)
            )
            row = (await session.execute(stmt)).first()
            if not row:
                raise ValueError(f"fixture not found for research: {fixture_id}")
            fixture, home_team, away_team = row[0], row[1], row[2]

        forecast_phase = (
            ForecastPhase.PREMATCH
            if phase == ForecastPhase.PREMATCH.value
            else ForecastPhase.MORNING
        )

        # 2. Build deterministic queries
        max_q = ctx.settings.research_max_queries_per_fixture
        queries = build_research_queries(
            home_team_name=home_team.name,
            away_team_name=away_team.name,
            kickoff_at=fixture.kickoff_at,
            phase=forecast_phase,
            max_queries=max_q,
        )

        all_raw_results: list[dict[str, Any]] = []
        raw_items: list[SearchResultItem] = []
        latest_retrieved_at = datetime.now(UTC)
        rate_headers: dict[str, str] = {}

        # 3. Execute bounded queries
        for query in queries:
            resp = await provider.search(
                query, max_results=ctx.settings.research_max_results_per_query
            )
            latest_retrieved_at = max(latest_retrieved_at, resp.retrieved_at)
            if resp.rate_limit_headers:
                rate_headers.update(resp.rate_limit_headers)
            if resp.raw_payload:
                all_raw_results.append(resp.raw_payload)
            raw_items.extend(resp.results)

        # 4. Deduplicate candidate documents
        deduped_docs = deduplicate_search_results(raw_items)

        # 5. Extract claims for each document
        doc_claim_map: dict[str, list[ExtractedClaimDTO]] = {}
        all_claims: list[ExtractedClaimDTO] = []

        for doc in deduped_docs:
            claims = await self.extractor.extract_claims(
                doc,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                home_team_name=home_team.name,
                away_team_name=away_team.name,
            )
            doc_key = normalize_url(doc.url)
            doc_claim_map[doc_key] = claims
            all_claims.extend(claims)

        # 6. Conflict detection
        conflicted_claims = detect_conflicts(all_claims)
        conflicts_count = sum(1 for c in conflicted_claims if c.conflict_flag)

        # Re-assign conflicted claims back to documents
        # Map by claim text for lookup
        conflicted_by_text = {c.claim_text: c for c in conflicted_claims}

        normalized_docs: list[dict[str, Any]] = []
        for doc in deduped_docs:
            doc_key = normalize_url(doc.url)
            original_claims = doc_claim_map.get(doc_key, [])
            updated_claims = [conflicted_by_text.get(c.claim_text, c) for c in original_claims]
            normalized_docs.append(
                {
                    "url": doc.url,
                    "domain": doc.domain,
                    "title": doc.title,
                    "published_at": doc.published_at.isoformat() if doc.published_at else None,
                    "retrieved_at": doc.retrieved_at.isoformat(),
                    "content_hash": content_sha256(doc.content or doc.title),
                    "relevance_score": doc.score,
                    "snippet": doc.content[:1000] if doc.content else None,
                    "provider": provider.name,
                    "metadata": doc.provider_metadata,
                    "claims": [
                        {
                            "claim_type": (
                                c.claim_type.value
                                if isinstance(c.claim_type, ClaimType)
                                else str(c.claim_type)
                            ),
                            "claim_text": c.claim_text,
                            "confidence": c.confidence,
                            "team_id": str(c.team_id) if c.team_id else None,
                            "valid_from": c.valid_from.isoformat() if c.valid_from else None,
                            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
                            "conflict_flag": c.conflict_flag,
                            "conflicting_claim_id": (
                                str(c.conflicting_claim_id) if c.conflicting_claim_id else None
                            ),
                            "extraction_version": c.extraction_version,
                            "metadata": c.metadata,
                        }
                        for c in updated_claims
                    ],
                }
            )

        # 7. Research status determination
        if not deduped_docs or not all_claims:
            status = ResearchState.NO_USEFUL_RESULTS
        else:
            status = ResearchState.AVAILABLE

        normalized = {
            "fixture_id": str(fid),
            "phase": phase,
            "status": status.value,
            "provider": provider.name,
            "queries": queries,
            "queries_count": len(queries),
            "documents_count": len(deduped_docs),
            "claims_count": len(all_claims),
            "conflicts_count": conflicts_count,
            "documents": normalized_docs,
        }

        return CollectorResult(
            raw_payload={"queries": queries, "raw_responses": all_raw_results},
            normalized=normalized,
            rate_headers=rate_headers,
            retrieved_at=latest_retrieved_at,
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
        phase: str = ForecastPhase.MORNING.value,
        **_: Any,
    ) -> tuple[SnapshotRef, ...]:
        fid = _uuid.UUID(str(fixture_id))
        norm = result.normalized
        provider_name = str(norm.get("provider", ctx.provider_name()))

        async with ctx.session_factory() as session:
            # 1. Insert ResearchRun
            run_id = _uuid.uuid4()
            run = ResearchRun(
                id=run_id,
                fixture_id=fid,
                phase=phase,
                status=str(norm.get("status", ResearchState.AVAILABLE.value)),
                provider=provider_name,
                queries_count=int(norm.get("queries_count", 0)),
                documents_count=int(norm.get("documents_count", 0)),
                claims_count=int(norm.get("claims_count", 0)),
                conflicts_count=int(norm.get("conflicts_count", 0)),
                captured_at=captured_at,
                details_jsonb={
                    "queries": norm.get("queries", []),
                    "payload_id": str(payload_id) if payload_id else None,
                    "source_fingerprint": source_fingerprint,
                },
                created_at=datetime.now(UTC),
            )
            session.add(run)
            await session.flush()

            # 2. Insert ResearchDocuments
            docs_data = norm.get("documents", [])
            doc_items: list[tuple[dict[str, Any], _uuid.UUID]] = []
            for doc_dict in docs_data:
                doc_id = _uuid.uuid4()
                pub_at_str = doc_dict.get("published_at")
                pub_at = datetime.fromisoformat(pub_at_str) if pub_at_str else None

                ret_at_str = doc_dict.get("retrieved_at")
                ret_at = datetime.fromisoformat(ret_at_str) if ret_at_str else captured_at

                doc_row = ResearchDocument(
                    id=doc_id,
                    fixture_id=fid,
                    run_id=run_id,
                    url=str(doc_dict.get("url", "")),
                    domain=str(doc_dict.get("domain", "")),
                    title=str(doc_dict.get("title", "")),
                    published_at=pub_at,
                    retrieved_at=ret_at,
                    content_hash=str(doc_dict.get("content_hash", "")),
                    relevance_score=doc_dict.get("relevance_score"),
                    snippet=doc_dict.get("snippet"),
                    provider=provider_name,
                    metadata_jsonb=doc_dict.get("metadata", {}),
                    created_at=datetime.now(UTC),
                )
                session.add(doc_row)
                doc_items.append((doc_dict, doc_id))

            await session.flush()

            # 3. Insert ResearchClaims
            for doc_dict, doc_id in doc_items:
                claims_data = doc_dict.get("claims", [])
                for claim_dict in claims_data:
                    claim_id = _uuid.uuid4()
                    team_id_raw = claim_dict.get("team_id")
                    team_id = _uuid.UUID(str(team_id_raw)) if team_id_raw else None

                    v_from_str = claim_dict.get("valid_from")
                    v_from = datetime.fromisoformat(v_from_str) if v_from_str else None
                    v_until_str = claim_dict.get("valid_until")
                    v_until = datetime.fromisoformat(v_until_str) if v_until_str else None

                    claim_row = ResearchClaim(
                        id=claim_id,
                        document_id=doc_id,
                        fixture_id=fid,
                        team_id=team_id,
                        claim_type=str(claim_dict.get("claim_type", "other")),
                        claim_text=str(claim_dict.get("claim_text", "")),
                        confidence=float(claim_dict.get("confidence", 0.8)),
                        valid_from=v_from,
                        valid_until=v_until,
                        conflict_flag=bool(claim_dict.get("conflict_flag", False)),
                        conflicting_claim_id=(
                            _uuid.UUID(str(claim_dict["conflicting_claim_id"]))
                            if claim_dict.get("conflicting_claim_id")
                            else None
                        ),
                        extraction_version=str(claim_dict.get("extraction_version", "v1_rule")),
                        metadata_jsonb=claim_dict.get("metadata", {}),
                        created_at=datetime.now(UTC),
                    )
                    session.add(claim_row)

            await session.commit()

        return (
            SnapshotRef(
                table="research_runs",
                snapshot_id=run_id,
                captured_at=captured_at,
            ),
        )


register(ResearchCollector())
