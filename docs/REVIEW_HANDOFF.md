# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES (Milestone M5.1 correctness pass completed, fully tested)  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M5.1 — Web Research Subsystem Correctness Pass  
**Review target branch:** `build/m5`  
**Review target commit:** `147862f` (Milestone M5.1 HEAD)  
**Previous accepted state:** `main` = `2e4683a` (`v0.5-m4` accepted M4 merge)  
**Previous M5 review verdict:** FAIL (HEAD `6c52b1f1df85163b0aeef1f3a16d223bd3296cff`)  
**Review scope:** diff `main..build/m5`

---

# Milestone M5.1 Specification Alignment & Fixes

Following independent review verdict `M5 = FAIL`, M5.1 implemented seven focused correctness fixes without broadly redesigning the accepted M5 architecture:

### 1. Point-in-Time Anti-Leakage: Tavily `retrieved_at` Precision
- **Defect fixed**: `retrieved_at` was previously recorded prior to awaiting the HTTP response, allowing pre-request timestamps to become visible before network reception.
- **Implementation**: In `TavilySearchProvider.search()`, `retrieved_at = self._clock()` is assigned strictly *after* `response = await self._client.post(...)`. Added injectable `clock` parameter for regression testing.
- **Verification**: `test_tavily_retrieval_time_captured_after_response_anti_leakage` verifies that injected response delays place `retrieved_at` at or after post-response completion time.

### 2. Claim-Level Temporal Safety & Indexing
- **Defect fixed**: Claims lacked an explicit `extracted_at` field and relied on parent document timestamps, risking temporal leakage if claim extraction occurred asynchronously or later than document retrieval.
- **Implementation**:
  - Added `extracted_at: datetime` (timezone-aware UTC) to `ResearchClaim` model, `ExtractedClaimDTO`, and `ResearchClaimOut` schema.
  - Added composite index `ix_research_claims_fixture_extracted` on `(fixture_id, extracted_at DESC)`.
  - Added Alembic migration `0007_m51_claim_extracted_at_and_fk.py` with clean upgrade and downgrade.
  - In `get_research_for_fixture()`, claims extracted after `as_of` are filtered out (`claim.extracted_at <= as_of`).
- **Verification**: `test_claim_level_as_of_safety_filtering` and `test_claim_level_as_of_filtering_integration` verify that claims extracted after `as_of` are excluded even if parent documents were retrieved before `as_of`.

### 3. Search Quota & Ledger Matching Real HTTP Calls
- **Defect fixed**: Outer collector framework reserved 1 quota unit for the entire job, while inner search loop made multiple HTTP requests without matching ledger records, leading to ledger mismatch and quota double-charging.
- **Implementation**:
  - `ResearchCollector.owns_quota = True`, notifying the outer framework (`run_collector()`) to bypass outer quota reservation and ledger recording.
  - `ResearchCollector` executes up to 6 bounded queries, invoking `ctx.quota.reserve(provider, priority, estimated_cost=1)` and `ctx.quota.record_success()` / `record_failure()` per individual query.
  - When quota is denied mid-run, execution halts cleanly before subsequent queries (e.g. stops before 3rd query when quota only allows 2).
  - If research is fresh under the coalescing lock, the collector exits early without issuing any quota requests or provider calls.
- **Verification**: `test_research_collector_records_exact_queries_in_ledger`, `test_research_collector_stops_when_quota_exhausted`, and `test_fresh_research_issues_zero_search_calls`.

### 4. Conflict Referential Integrity with Deferred Foreign Key
- **Defect fixed**: Conflicted claims generated new UUIDs during conflict detection, breaking foreign key relationships, and PostgreSQL lacked a formal self-referential foreign key constraint.
- **Implementation**:
  - `ResearchClaim.conflicting_claim_id` constrained by `ForeignKey("research_claims.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED")`.
  - Stable claim IDs preserved end-to-end throughout extraction and conflict flagging.
  - Opposing claims reciprocally reference each other (`A.conflicting_claim_id == B.id` and `B.conflicting_claim_id == A.id`).
- **Verification**: `test_research_collector_flags_conflicts` verifies that reciprocal foreign keys persist cleanly in PostgreSQL and can be fetched via `session.get(ResearchClaim, ...)`.

### 5. SearchProvider Resource Cleanup
- **Defect fixed**: `SearchProvider` was instantiated at worker module level or not reliably closed on error paths; unrelated providers (`sports_provider`, `odds_provider`) were unnecessarily constructed for research jobs.
- **Implementation**:
  - In `sports_intelligence.workers.tasks.collect._run_collect_job()`, only the provider required for `collector_name` is built. Unrelated providers remain uninstantiated.
  - `search_provider.aclose()` is guaranteed inside the `finally` block across all scenarios: success, quota denial, provider network error, and DB persistence failure.
- **Verification**: Parameterized unit test `test_run_collect_job_always_closes_search_provider` across all 4 scenarios.

### 6. Semantically Structured Research States
- **Defect fixed**: Various non-available states were collapsed into generic empty result states.
- **Implementation**: Formally implemented distinct `ResearchState` enum values:
  - `DISABLED`: Research globally disabled or search provider unconfigured.
  - `PROVIDER_ERROR`: Network/API exception occurred during provider execution.
  - `NO_USEFUL_RESULTS`: Provider queries succeeded but returned 0 results or quota halted before any results.
  - `EXTRACTION_UNAVAILABLE`: Documents retrieved, but claim extraction disabled or failed.
  - `AVAILABLE`: Documents and claims successfully collected.
- **Verification**: `test_research_collector_disabled_returns_disabled_state`, `test_research_collector_handles_provider_error`, and `test_research_collector_structured_states`.

### 7. Historical View Consistency Contract
- **Defect fixed**: Replay queries risked mixing run statuses with documents across different collection runs.
- **Implementation**:
  - `get_research_for_fixture(fixture_id, as_of=..., mode="latest_run")`:
    - Default Option B (`mode="latest_run"`): Locates the latest `ResearchRun` at or before `as_of`. Filters documents to `ResearchDocument.run_id == run_row.id`, matching the run's exact status.
    - Option A (`mode="accumulated"`): Accumulates all historical documents and claims at or before `as_of`.
  - Supported via `?mode=latest_run|accumulated` query parameter in `GET /v1/fixtures/{fixture_id}/research`.
- **Verification**: `test_research_api_anti_leakage_as_of` tests both modes and asserts point-in-time boundaries.

---

# Verification Evidence (All Passing Locally)

- **Unit tests**: `uv run pytest -q -m "not integration"` → **308 passed, 71 deselected in 12.75s**
- **Integration tests**: `TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" uv run pytest -q -m integration` → **71 passed, 308 deselected in 18.29s**
- **Full test suite**: `uv run pytest -q` → **379 passed in 20.18s**
- **Linter**: `uv run ruff check .` → **clean (All checks passed!)**
- **Formatter**: `uv run ruff format --check .` → **clean (157 files already formatted)**
- **Type checker**: `uv run mypy src` → **clean (Success: no issues found in 104 source files)**
- **Alembic check**: `uv run alembic check` → **clean (No new upgrade operations detected)**
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` → **clean (OK)**
- **Secret scan**: clean (zero credentials in code, diff, or Git).
- **Offline safety**: Zero live external search API calls during test suite execution.

---

# Instructions for Independent Reviewer

1. Inspect git diff against `main` (`git diff main..build/m5`) or against reviewed HEAD `6c52b1f1df85163b0aeef1f3a16d223bd3296cff`.
2. Inspect migration `0007_m51_claim_extracted_at_and_fk.py` and run `alembic check`.
3. Verify that `TavilySearchProvider.search()` captures `retrieved_at` after `post()`.
4. Verify reciprocal foreign key integrity on `ResearchClaim.conflicting_claim_id`.
5. Verify per-search-request quota accounting and ledger tracking in `ResearchCollector`.
6. Run `uv run pytest -q` to verify all 379 tests pass.
7. Do NOT merge `build/m5` into `main`.
8. Do NOT start Milestone M6.