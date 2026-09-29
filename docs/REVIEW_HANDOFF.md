# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES (Milestone M5 implemented, fully tested, ready for review)  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M5 — Web Research Subsystem  
**Review target branch:** `build/m5`  
**Review target commit:** `e0d18a7d599af0c559fb85d16f1623f211a4894c`  
**Previous accepted state:** `main` = `2e4683a` (`v0.5-m4` accepted M4 merge)  
**Review scope:** diff `main..build/m5` (Milestone M5 changes)

---

# Milestone M5 Specification Alignment

Implemented strictly per authoritative project specifications:
- `08_FOOTBALL_ANALYTICS_PIPELINE.md`
- `09_AGENT_CATALOG_AND_ORCHESTRATION.md`
- `10_DATABASE_AND_DATA_LIFECYCLE.md`
- `11_API_QUOTA_CACHING_STRATEGY.md`
- `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`

### Architecture Boundaries & Invariants Enforced
- **Zero Prediction / Probability Logic in M5**: Web research is an evidence collector and claim extractor only. MatchContext assembly and LLM prediction routing are reserved for M7.
- **Graceful Degradation / Optionality**: Web research is fully optional. When `SEARCH_PROVIDER` is disabled or empty, or `RESEARCH_ENABLED=False`, zero external provider requests are made, and pre-match scan/fixtures pipelines operate normally.
- **Strict Anti-Leakage / Provenance**: All research documents and claims are timestamped with `retrieved_at` and `published_at`. Point-in-time querying via `as_of` filters out any information retrieved or published after the audit cutoff (`retrieved_at <= as_of` and `published_at <= as_of`).
- **Conflict Preservation**: Contradictory claims (e.g. player ruled out vs passed fitness test) are never deleted, overwritten, or silently merged. Both opposing claims are persisted, flagged with `conflict_flag=True`, cross-referenced via `conflicting_claim_id`, and documented with metadata for downstream Data Quality assessment.
- **Zero Live Search API Calls in Tests/CI**: Fully tested offline with `MockSearchProvider`.

---

# What Changed in M5

## 1. Search Provider Boundary & Adapters
- `src/sports_intelligence/providers/search/base.py`:
  - `SearchProvider` async protocol (`search(query, max_results=5) -> SearchResponse`).
  - DTOs: `SearchResultItem`, `SearchResponse`.
- `src/sports_intelligence/providers/search/mock.py`:
  - `MockSearchProvider`: deterministic offline provider with canned responses, query fallbacks, error simulation, query history tracking, and JSON-serializable raw payloads.
- `src/sports_intelligence/providers/search/tavily.py`:
  - `TavilySearchProvider`: production adapter with bounded timeouts, retries (up to 3 attempts with exponential backoff and jitter), 4xx non-retryable handling, canonical URL normalization, secret redaction, and rate limit header parsing.
- `src/sports_intelligence/providers/search/factory.py`:
  - Strict gating: refuses silent mock in `sandbox`/`live_local` unless `search_allow_mock_override=True`.

## 2. Claim Extraction, Conflict Detection & Anti-Leakage
- `src/sports_intelligence/research/query_builder.py`:
  - `build_research_queries`: bounded (max 6), deterministic queries per fixture based on team names, kickoff date, and phase (`morning` preparation vs `prematch` lineup/fitness refresh).
- `src/sports_intelligence/research/dedup.py`:
  - `deduplicate_search_results`, `normalize_url` (strips tracking parameters, query fragments, trailing slashes), `content_sha256`.
- `src/sports_intelligence/research/extractor.py`:
  - `RuleBasedClaimExtractor` / `MockClaimExtractor`: extracts claims across 8 categories (`AVAILABILITY`, `SUSPENSION`, `ROTATION`, `LINEUP`, `MANAGER_STATEMENT`, `TACTICAL`, `TRAVEL`, `TEAM_NEWS`), assigns team ownership, confidence scores, and extraction metadata.
- `src/sports_intelligence/research/conflict.py`:
  - `detect_conflicts`: detects contradictory claims (e.g. absent vs present for the same subject/player or team); strictly preserves both claims, flags `conflict_flag=True`, links `conflicting_claim_id`, and attaches audit metadata.
- `src/sports_intelligence/research/service.py`:
  - `get_research_for_fixture`: anti-leakage audit service enforcing `as_of` temporal filtering (`retrieved_at <= as_of` and `published_at <= as_of`) for historical replay and point-in-time consistency.

## 3. Database Persistence & Migrations
- `src/sports_intelligence/db/models/snapshots.py`:
  - Models: `ResearchRun`, `ResearchDocument`, `ResearchClaim` with descending composite indexes (`ix_research_runs_fixture_captured`, `ix_research_docs_fixture_retrieved`, `ix_research_claims_fixture_type`) and foreign keys.
- `src/sports_intelligence/db/migrations/versions/0006_m5_research_documents_claims.py`:
  - Clean upgrade/downgrade migration for research tables, indexes, and constraints. Verified by `alembic check`.

## 4. Collector & Workers Framework Integration
- `src/sports_intelligence/collectors/research_collector.py`:
  - Registered collector (`name="research"`, `category=FreshnessCategory.RESEARCH`, `priority=Priority.P3`), supports coalescing locks (`research:{fixture_id}`), raw payload storage in `raw_provider_payloads`, and snapshot persistence.
- `src/sports_intelligence/collectors/pre_match_scan.py`:
  - Pre-match scanner includes `FreshnessCategory.RESEARCH` in scan plan and TTL evaluations.
- `src/sports_intelligence/workers/tasks/research.py`:
  - Celery task routed to `research_io` queue.

## 5. REST API Routes
- `src/sports_intelligence/api/routes/research.py`:
  - `GET /v1/fixtures/{fixture_id}/research`: returns documents and claims with optional `as_of` query parameter.
- `src/sports_intelligence/api/routes/status.py`:
  - `GET /v1/fixtures/{fixture_id}/status`: reflects `research` category freshness state (`fresh`, `stale`, `unknown`) and last refresh timestamp.

---

# Verification Evidence (Local Execution)

- **Live Tavily Smoke**: VERIFIED (PASS)
  - Exactly 2 real Tavily API requests executed (1 provider query check + 1 collector-driven run for real fixture `Brentford vs Tottenham`).
  - RFC 2822 HTTP publication date parsing supported and verified (`_parse_published_at`).
  - `ResearchRun` and 3 `ResearchDocument` records persisted; 8 `ResearchClaim` records extracted.
  - Strict anti-leakage `as_of` temporal query verified (`as_of=now` → 3 docs / 8 claims; `as_of=past` → 0 docs / 0 claims).
  - Secret scan: clean (zero credentials in `RawProviderPayload`, `ResearchDocument`, or Git diff).
- **Unit tests**: `uv run pytest -q -m "not integration"` → **300 passed, 66 deselected in 4.19s**
- **Integration tests**: `TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" uv run pytest -q -m integration` → **66 passed, 300 deselected in 10.48s**
- **Full test suite**: `uv run pytest -q` → **366 passed in 14.06s**
- **Linter**: `uv run ruff check .` → **clean (All checks passed!)**
- **Formatter**: `uv run ruff format --check .` → **clean (156 files already formatted)**
- **Type checker**: `uv run mypy src` → **clean (Success: no issues found in 103 source files)**
- **Alembic check**: `uv run alembic check` → **clean (No new upgrade operations detected)**
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` → **clean (OK)**
- **Secret check**: clean, zero credentials in code or Git.

---

# Instructions for Independent Reviewer

1. Verify git diff against `main` (`git diff main..build/m5`).
2. Verify that no prediction, betting, or probability code exists in M5.
3. Verify that `MockSearchProvider` is strictly used in CI/unit tests, with zero external network access.
4. Verify anti-leakage temporal filtering (`as_of` queries) and conflict preservation logic.
5. Verify schema synchronization (`alembic check`).
6. Do NOT merge `build/m5` into `main` without explicit verdict.
7. Do NOT start Milestone M6.