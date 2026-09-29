# Current Task

**Status:** COMPLETE (Milestone M5 implemented, live validated with Tavily, fully tested, ready for independent review)
**Milestone:** M5 — Web Research Subsystem
**Branch:** `build/m5`
**Owner/agent:** Antigravity (Gemini 3.8 Flash)
**Started at:** 2026-09-29
**Last updated:** 2026-09-29

---

# Milestone Objective

Implement the bounded, testable, anti-leakage pre-match web research subsystem per authoritative specifications:
- `08_FOOTBALL_ANALYTICS_PIPELINE.md`
- `09_AGENT_CATALOG_AND_ORCHESTRATION.md`
- `10_DATABASE_AND_DATA_LIFECYCLE.md`
- `11_API_QUOTA_CACHING_STRATEGY.md`
- `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`

### Hard Guardrails & Discipline
1. **Local Development Only**: No Hetzner, no SSH, no Hermes, no production deployments.
2. **Subsystem Isolation**: Web research is an evidence-gathering subsystem only. No predictions, forecasts, betting logic, no-vig calculations, or MatchContext assembly are included in M5 (reserved for M7).
3. **Graceful Degradation / Optionality**: Web research must be completely optional. When `SEARCH_PROVIDER` is disabled or empty, or `RESEARCH_ENABLED=False`, zero external searches run, and the pipeline continues normally.
4. **Zero Live Search API Calls in Normal Tests/CI**: Fully mocked offline execution via `MockSearchProvider` for all automated suites.

---

# Subsystems Implemented

1. **Search Provider Boundary & Adapters (`src/sports_intelligence/providers/search/`)**:
   - `SearchProvider` Protocol: `search(query, max_results=5) -> SearchResponse`.
   - DTOs: `SearchResultItem`, `SearchResponse`.
   - `MockSearchProvider`: deterministic offline search provider with canned query responses, query token fallbacks, simulated errors, call history, and JSON-safe raw payload serialization.
   - `TavilySearchProvider`: production-ready adapter for Tavily Search API with bounded timeouts, retries (up to 3 attempts with exponential backoff and jitter), 4xx non-retryable handling, canonical URL normalization, secret redaction in logging/payloads, RFC 2822 date parsing, and rate limit header parsing.
   - Provider factory `build_search_provider()`: strict gating based on `app_env`, `search_provider`, and `search_api_key`. Refuses silent mock in live environments without explicit override.

2. **Core Domain Models & Extractor (`src/sports_intelligence/research/`)**:
   - `ExtractedClaimDTO`, `ResearchDocumentDTO`, `ResearchRunResultDTO`.
   - `build_research_queries`: bounded (max 6), deterministic queries per fixture based on team names, kickoff date, and phase (`morning` preparation vs `prematch` lineup/fitness refresh).
   - `deduplicate_search_results`, `normalize_url` (strips tracking parameters, query fragments, trailing slashes), `content_sha256`.
   - `RuleBasedClaimExtractor` / `MockClaimExtractor`: extracts claims across 8 categories (`AVAILABILITY`, `SUSPENSION`, `ROTATION`, `LINEUP`, `MANAGER_STATEMENT`, `TACTICAL`, `TRAVEL`, `TEAM_NEWS`), assigns team ownership, confidence scores, and extraction metadata.
   - `detect_conflicts`: detects contradictory claims (e.g. absent vs present for the same subject/player or team); strictly preserves both claims, flags `conflict_flag=True`, links `conflicting_claim_id`, and attaches audit metadata (never discards or merges contradictory claims).
   - `get_research_for_fixture`: anti-leakage audit service enforcing `as_of` temporal filtering (`retrieved_at <= as_of` and `published_at <= as_of`) for historical replay and point-in-time consistency.

3. **Database Persistence & Migrations (`src/sports_intelligence/db/`)**:
   - Models: `ResearchRun`, `ResearchDocument`, `ResearchClaim` with descending composite indexes (`ix_research_runs_fixture_captured`, `ix_research_docs_fixture_retrieved`, `ix_research_claims_fixture_type`) and foreign keys.
   - Alembic Migration `0006_m5_research_documents_claims.py`: clean downgrade and upgrade, fully verified by `alembic check`.

4. **Collector & Pipeline Integration (`src/sports_intelligence/collectors/` & `workers/`)**:
   - `ResearchCollector`: registered in framework (`name="research"`, `category=FreshnessCategory.RESEARCH`, `priority=Priority.P3`), supports coalescing locks (`research:{fixture_id}`), raw payload storage in `raw_provider_payloads`, and snapshot persistence.
   - Pre-match scanner: includes `FreshnessCategory.RESEARCH` in scan plan and TTL evaluations.
   - Celery tasks: `sports_intelligence.workers.tasks.research` routed to `research_io` queue.

5. **REST API Routes (`src/sports_intelligence/api/`)**:
   - `GET /v1/fixtures/{fixture_id}/research`: returns documents and claims with optional `as_of` query parameter.
   - `GET /v1/fixtures/{fixture_id}/status`: reflects `research` category freshness state (`fresh`, `stale`, `unknown`) and last refresh timestamp.

---

# Live Tavily Validation (Completed)

- **Tavily Live Adapter Status**: VERIFIED (PASS).
- **Exact real Tavily API requests made**: 2 requests total (1 provider-level query check + 1 bounded collector run for real DB fixture).
- **Real fixture used**: `8c9c59c9-9ad9-4683-9895-5db48d2a52b0` (Brentford vs Tottenham, kickoff 2026-08-22).
- **Queries executed**:
  1. `"Brentford vs Tottenham injury news"` (provider contract test)
  2. `"Brentford injuries 2026-08-22"` (collector fixture test)
- **Real response contract findings**:
  - Tavily returns RFC 2822 / HTTP format date strings in `published_date` (e.g. `Sat, 22 Aug 2026 00:00:00 GMT`), which was not parsed by ISO-only parser.
  - Fix implemented: Added RFC 2822 parsing via `email.utils.parsedate_to_datetime` in `_parse_published_at`, producing valid timezone-aware UTC datetimes.
  - Also added result `id` extraction into `provider_metadata["tavily_id"]`.
- **Quality sanity check**:
  - Returned authoritative, domain-relevant sources (Goal.com, The Athletic / NYT, Reuters).
  - Plausibly useful for team news / injuries: identified specific player availability (e.g. Kulusevski, Romero, Vicario, Maddison, Solanke for Tottenham, and Yarmoliuk, Van den Berg for Brentford).
- **Database persistence**:
  - `ResearchRun` created: `status=AVAILABLE`, `queries_count=1`, `documents_count=3`, `claims_count=8`.
  - 3 `ResearchDocument` records persisted with genuine `retrieved_at`, parsed `published_at`, `content_hash`, and metadata.
  - 8 `ResearchClaim` records persisted across `availability`, `suspension`, and `team_news`.
- **Anti-leakage audit**:
  - `get_research_for_fixture(as_of=now)` returned 3 documents and 8 claims.
  - `get_research_for_fixture(as_of=past)` returned 0 documents and 0 claims.
- **Secret safety audit**:
  - Verified `RawProviderPayload` table has zero credentials stored.
  - Verified `ResearchDocument` and `ResearchClaim` rows have zero credentials stored.

---

# Verification (All passing locally)

- **Unit tests**: `uv run pytest -q -m "not integration"` → **300 passed, 66 deselected in 4.19s**
- **Integration tests**: `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration` → **66 passed, 300 deselected in 10.48s**
- **Full test suite**: `uv run pytest -q` → **366 passed in 14.06s**
- **Linter**: `uv run ruff check .` → **clean (All checks passed!)**
- **Formatter**: `uv run ruff format --check .` → **clean (156 files already formatted)**
- **Type checker**: `uv run mypy src` → **clean (Success: no issues found in 103 source files)**
- **Alembic**: `uv run alembic check` → **clean (No new upgrade operations detected)**
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` → **clean (OK)**
- **Secret check**: clean, zero credentials in code or Git.

---

# Handoff

Milestone M5 is complete, live validated, fully tested, and ready on branch `build/m5` for independent review.
Do not merge `build/m5` to `main`. Do not start M6.