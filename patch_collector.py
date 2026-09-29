import re

with open("src/sports_intelligence/collectors/research_collector.py") as f:
    content = f.read()

# Fix 4: latest_snapshot
content = re.sub(
    r"async def latest_snapshot.*?\n        row = \(await session\.execute\(stmt\)\)\.first\(\)\n        return \(row\[0\], row\[1\]\) if row else \(None, None\)",
    r"""async def latest_snapshot(
        self, session: AsyncSession, *, fixture_id: object, **_: Any
    ) -> tuple[datetime | None, _uuid.UUID | None]:
        fid = _uuid.UUID(str(fixture_id))
        stmt = (
            select(ResearchRun.captured_at, ResearchRun.id, ResearchRun.status)
            .where(ResearchRun.fixture_id == fid)
            .order_by(ResearchRun.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        if not row:
            return (None, None)
        captured_at, run_id, status = row[0], row[1], row[2]
        if status == ResearchState.PROVIDER_ERROR.value:
            return (None, None)
        return (captured_at, run_id)""",
    content,
    flags=re.DOTALL
)

# Fix 1 and 5: Retry loop and partial_failure
old_fetch_loop = """        # 3. Execute bounded queries with per-request quota protection & ledger
        for query in queries:
            # Per-query quota gate BEFORE dispatching HTTP request
            decision = await ctx.quota.reserve(
                provider=provider.name,
                priority=self.priority,
                estimated_cost=1,
            )
            if decision.denied:
                logger.warning(
                    "search query quota denied; stopping further queries",
                    extra={"query": query, "reason": decision.reason},
                )
                break

            q_start = datetime.now(UTC)
            try:
                resp = await provider.search(
                    query, max_results=ctx.settings.research_max_results_per_query
                )
                q_end = datetime.now(UTC)
                await ctx.quota.record_success(
                    provider=provider.name,
                    endpoint_category="research",
                    started_at=q_start,
                    finished_at=q_end,
                    headers=resp.rate_limit_headers,
                    priority=self.priority,
                    estimated_cost=1,
                    fixture_id=fid,
                )
                queries_executed.append(query)
                latest_retrieved_at = max(latest_retrieved_at, resp.retrieved_at)
                if resp.rate_limit_headers:
                    rate_headers.update(resp.rate_limit_headers)
                if resp.raw_payload:
                    all_raw_results.append(resp.raw_payload)
                raw_items.extend(resp.results)
            except Exception as exc:
                q_end = datetime.now(UTC)
                await ctx.quota.record_failure(
                    provider=provider.name,
                    endpoint_category="research",
                    started_at=q_start,
                    exc=exc,
                    headers=getattr(exc, "quota_headers", None),
                    priority=self.priority,
                    estimated_cost=1,
                    fixture_id=fid,
                )
                logger.warning(
                    "research search query failed",
                    extra={"query": query, "error": str(exc)},
                    exc_info=True,
                )
                provider_error = exc
                break

        # If provider failed and no raw items were retrieved, record PROVIDER_ERROR
        if provider_error is not None and not raw_items:"""

new_fetch_loop = """        # 3. Execute bounded queries with per-request quota protection & ledger
        MAX_SEARCH_ATTEMPTS = 3
        import asyncio
        from sports_intelligence.providers.errors import (
            ProviderRateLimitError,
            ProviderServerError,
            ProviderTimeoutError,
            ProviderTransportError,
        )
        RETRYABLE_PROVIDER_ERRORS = (
            ProviderRateLimitError,
            ProviderServerError,
            ProviderTimeoutError,
            ProviderTransportError,
        )

        for query in queries:
            query_success = False
            for attempt in range(MAX_SEARCH_ATTEMPTS):
                # Per-query quota gate BEFORE dispatching HTTP request
                decision = await ctx.quota.reserve(
                    provider=provider.name,
                    priority=self.priority,
                    estimated_cost=1,
                )
                if decision.denied:
                    logger.warning(
                        "search query quota denied; stopping further queries",
                        extra={"query": query, "reason": decision.reason},
                    )
                    break

                q_start = datetime.now(UTC)
                try:
                    resp = await provider.search(
                        query, max_results=ctx.settings.research_max_results_per_query
                    )
                    q_end = datetime.now(UTC)
                    await ctx.quota.record_success(
                        provider=provider.name,
                        endpoint_category="research",
                        started_at=q_start,
                        finished_at=q_end,
                        headers=resp.rate_limit_headers,
                        priority=self.priority,
                        estimated_cost=1,
                        fixture_id=fid,
                    )
                    queries_executed.append(query)
                    latest_retrieved_at = max(latest_retrieved_at, resp.retrieved_at)
                    if resp.rate_limit_headers:
                        rate_headers.update(resp.rate_limit_headers)
                    if resp.raw_payload:
                        all_raw_results.append(resp.raw_payload)
                    raw_items.extend(resp.results)
                    query_success = True
                    break
                except Exception as exc:
                    q_end = datetime.now(UTC)
                    await ctx.quota.record_failure(
                        provider=provider.name,
                        endpoint_category="research",
                        started_at=q_start,
                        exc=exc,
                        headers=getattr(exc, "quota_headers", None),
                        priority=self.priority,
                        estimated_cost=1,
                        fixture_id=fid,
                    )
                    logger.warning(
                        "research search query failed",
                        extra={"query": query, "error": str(exc), "attempt": attempt + 1},
                        exc_info=True,
                    )
                    
                    if isinstance(exc, RETRYABLE_PROVIDER_ERRORS):
                        if attempt < MAX_SEARCH_ATTEMPTS - 1:
                            await asyncio.sleep(0.1 * (2 ** attempt))
                            continue
                        else:
                            provider_error = exc
                            break
                    else:
                        provider_error = exc
                        break
                        
            if not query_success:
                # Need to also set provider_error if it's missing (e.g. quota denied)
                if provider_error is None:
                    provider_error = Exception("Query failed or quota denied")
                break

        partial_failure = provider_error is not None and bool(raw_items)

        # If provider failed and no raw items were retrieved, record PROVIDER_ERROR
        if provider_error is not None and not raw_items:"""

content = content.replace(old_fetch_loop, new_fetch_loop)

# Fix 2: EXTRACTION_UNAVAILABLE real configurable state
old_extraction_check = """        extraction_enabled = getattr(ctx.settings, "research_claim_extraction_enabled", True)
        if not extraction_enabled or self.extractor is None:"""
new_extraction_check = """        extraction_enabled = ctx.settings.research_claim_extraction_enabled
        if not extraction_enabled:"""
content = content.replace(old_extraction_check, new_extraction_check)

# Fix 5 continued: Partial Failure Status and Details
old_status_check = """        # 7. Research status determination
        if extraction_unavailable and deduped_docs:
            status = ResearchState.EXTRACTION_UNAVAILABLE
        elif not deduped_docs or not all_claims:
            status = ResearchState.NO_USEFUL_RESULTS
        else:
            status = ResearchState.AVAILABLE

        normalized = {
            "fixture_id": str(fid),
            "phase": phase,
            "status": status.value,
            "provider": provider.name,
            "queries": queries_executed,
            "queries_count": len(queries_executed),
            "documents_count": len(deduped_docs),
            "claims_count": len(all_claims),
            "conflicts_count": conflicts_count,
            "documents": normalized_docs,
        }"""

new_status_check = """        # 7. Research status determination
        if partial_failure:
            status = ResearchState.PROVIDER_ERROR
        elif extraction_unavailable and deduped_docs:
            status = ResearchState.EXTRACTION_UNAVAILABLE
        elif not deduped_docs or not all_claims:
            status = ResearchState.NO_USEFUL_RESULTS
        else:
            status = ResearchState.AVAILABLE

        normalized = {
            "fixture_id": str(fid),
            "phase": phase,
            "status": status.value,
            "provider": provider.name,
            "queries": queries_executed,
            "queries_count": len(queries_executed),
            "documents_count": len(deduped_docs),
            "claims_count": len(all_claims),
            "conflicts_count": conflicts_count,
            "documents": normalized_docs,
        }
        
        if provider_error is not None:
            normalized["details"] = {
                "queries_planned": len(queries),
                "queries_attempted": len(queries_executed) + 1,  # +1 for the failed one
                "queries_succeeded": len(queries_executed),
                "failed_query_count": 1,
                "partial_failure": partial_failure,
                "provider_error_class": provider_error.__class__.__name__,
            }"""
            
content = content.replace(old_status_check, new_status_check)

# Fix 5 continued: Persist details_jsonb
old_persist_details = """                details_jsonb={
                    "queries": norm.get("queries", []),
                    "payload_id": str(payload_id) if payload_id else None,
                    "source_fingerprint": source_fingerprint,
                },"""
new_persist_details = """                details_jsonb={
                    "queries": norm.get("queries", []),
                    "payload_id": str(payload_id) if payload_id else None,
                    "source_fingerprint": source_fingerprint,
                    **(norm.get("details", {})),
                },"""
content = content.replace(old_persist_details, new_persist_details)

with open("src/sports_intelligence/collectors/research_collector.py", "w") as f:
    f.write(content)

