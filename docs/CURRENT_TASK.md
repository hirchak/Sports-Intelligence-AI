# Current Task

**Status:** COMPLETE (Ready for independent review)  
**Milestone:** M5.1 — Web Research Subsystem Correctness & Anti-Leakage Pass  
**Branch:** `build/m5`  
**Owner/agent:** Antigravity (Gemini 3.8 Flash)  
**Started at:** 2026-09-29  
**Completed at:** 2026-09-29  

---

# Milestone Objective

Address all findings from the independent review of Milestone M5 (verdict `M5 = FAIL`) through a focused M5.1 correctness pass on `build/m5` without redesigning core architecture:
1. **Fix Tavily Retrieval Time / As-Of Leakage**: `retrieved_at` captured strictly after awaiting HTTP response completion.
2. **Claim-Level Temporal Safety**: Add `extracted_at` to `ResearchClaim`, index `ix_research_claims_fixture_extracted`, Alembic migration 0007, and filter `claim.extracted_at <= as_of`.
3. **Search Quota and Request Ledger Matching Real HTTP Calls**: `ResearchCollector` owns per-search-request accounting (`owns_quota = True`), per-query `reserve(cost=1)` / `record_success()` / `record_failure()`, graceful stop when quota exhausted, and zero calls when research is fresh.
4. **Fix Conflict Referential Integrity**: Stable claim IDs end-to-end, deferred self-referential FK (`fk_research_claims_conflicting_claim_id`), and reciprocal referential integrity queryable in PostgreSQL.
5. **SearchProvider Resource Cleanup**: Provider lifecycle closed in `_run_collect_job()` `finally` block across all scenarios (success, quota denied, provider error, DB error) without instantiating sports or odds providers.
6. **Structured Research States**: Semantically distinct `DISABLED`, `PROVIDER_ERROR`, `NO_USEFUL_RESULTS`, `EXTRACTION_UNAVAILABLE`, `AVAILABLE` states.
7. **Research Run and Historical View Consistency**: Default Option B (`mode="latest_run"`) returns evidence strictly belonging to the latest run at or before `as_of` without mixing run statuses and documents, with optional Option A (`mode="accumulated"`).
8. **Zero Unintended External Calls**: All automated tests run against deterministic mocks.

---

# Subsystems Implemented & Verified in M5.1

1. **Anti-Leakage & Retrieval Time Precision (`src/sports_intelligence/providers/search/`)**:
   - `TavilySearchProvider`: `retrieved_at = self._clock()` moved strictly *after* `response = await self._client.post(...)`. Added injectable `clock` for deterministic test verification.
   - `MockSearchProvider`: Added injectable `clock` parameter for test alignment.

2. **Claim-Level Temporal Safety & Option B Consistency (`src/sports_intelligence/research/`)**:
   - `ResearchClaim`: Added timezone-aware `extracted_at` column, populated from extractor execution timestamp.
   - Composite index: `ix_research_claims_fixture_extracted` on `(fixture_id, extracted_at DESC)`.
   - Migration `0007_m51_claim_extracted_at_and_fk.py`: Applied and verified clean bidirectional migration and `alembic check`.
   - `get_research_for_fixture()`: Added `mode: Literal["latest_run", "accumulated"] = "latest_run"`.
     - In `latest_run` mode (default Option B), resolves the latest `ResearchRun` at or before `as_of`, enforces `ResearchDocument.run_id == run_row.id`, and applies `doc.retrieved_at <= as_of`, `doc.published_at <= as_of`, and `claim.extracted_at <= as_of`.
     - In `accumulated` mode (Option A), queries all historical documents and claims at or before `as_of`.
   - REST API: Added `mode` query parameter to `GET /v1/fixtures/{fixture_id}/research`.

3. **Per-Query Quota Accounting & Request Ledger Alignment (`src/sports_intelligence/collectors/`)**:
   - `src/sports_intelligence/collectors/framework.py`: Checks `collector.owns_quota` to bypass generic outer reservation and ledger recording.
   - `ResearchCollector`: Sets `owns_quota = True`, `cost_estimate = 1`. Iterates through generated queries (up to 6), invoking `ctx.quota.reserve()` and `ctx.quota.record_success()` / `record_failure()` per query.
   - Graceful quota denial: Stops before executing further queries when quota is exhausted; persists any prior documents or marks `NO_USEFUL_RESULTS` if empty.
   - Cache bypass: If fresh research run exists within TTL, exits early issuing zero quota reservations or search provider calls.

4. **Conflict Referential Integrity (`src/sports_intelligence/db/models/snapshots.py` & `research/`)**:
   - Added self-referential foreign key `conflicting_claim_id` on `research_claims.id` with `DEFERRABLE INITIALLY DEFERRED` constraint.
   - Preserves stable claim UUIDs throughout extraction and conflict resolution.
   - Reciprocal integrity: Opposing claims point directly to each other (`claim_a.conflicting_claim_id == claim_b.id` and vice-versa) and are queryable directly in PostgreSQL.

5. **Resource Management & Worker Provider Scoping (`src/sports_intelligence/workers/tasks/collect.py`)**:
   - Scoped provider instantiation: Only instantiates `SearchProvider` when `collector_name == "research"`; sports and odds providers are not instantiated.
   - Guaranteed cleanup: `search_provider.aclose()` invoked in `finally` block across all execution paths.

6. **Structured Research States (`src/sports_intelligence/core/phases.py` & `collectors/`)**:
   - `DISABLED`: When research is disabled globally or search provider is unconfigured.
   - `PROVIDER_ERROR`: When provider queries fail with network/API exceptions and no results were obtained.
   - `NO_USEFUL_RESULTS`: When provider returned 0 items or quota halted before any results.
   - `EXTRACTION_UNAVAILABLE`: When documents were retrieved but claim extraction is disabled or failed.
   - `AVAILABLE`: When documents and claims were successfully retrieved and extracted.

---

# Verification Suite Results

All tests run locally in Docker Compose environment (PostgreSQL 16 on port 5433, Redis 7 on port 6380):
- **Full Test Suite**: `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q` → **379 passed in 20.18s**
- **Unit Suite**: `uv run pytest -q -m "not integration"` → **308 passed, 71 deselected in 12.75s**
- **Integration Suite**: `uv run pytest -q -m integration` → **71 passed, 308 deselected in 18.29s**
- **Linter**: `uv run ruff check .` → **All checks passed!**
- **Formatter**: `uv run ruff format --check .` → **157 files already formatted**
- **Type Checker**: `uv run mypy src` → **Success: no issues found in 104 source files**
- **Migration Check**: `uv run alembic check` → **No new upgrade operations detected**
- **Compose Configs**: `docker compose config -q` and `docker compose --profile telegram config -q` → **clean**
- **Secret Safety**: Scanned diff and commits; zero credentials found.
- **External Calls**: Zero real search provider requests during test suite execution.

---

# Handoff

Milestone M5.1 is complete and ready for independent acceptance review.
Do NOT merge `build/m5` into `main`. Do NOT start M6.