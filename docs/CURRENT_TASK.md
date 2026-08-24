# Current Task

**Status:** COMPLETE — awaiting independent review
**Milestone:** M4 — Automated Match Data Collection + Odds + Quota/Freshness
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode); continued by ox-alpha
**Started at:** 2026-08-21
**Last updated:** 2026-08-24

---

# Task

Implement M4 on `build/m4`: scheduler, pre-match scanner, freshness policy,
QuotaManager + ledger, request coalescing, sports/odds collectors,
odds provider boundary, migration 0004, job_attempts closure, status API.

---

# Acceptance criteria

- Scheduler: deterministic Celery Beat entries (09:00 discovery morning,
  13:00 refresh), configurable via settings, `scheduler_enabled=False`
  by default (quota-safe); pre-match scan toggle separate → OK
- Pre-match scanner reads DB only, decides categories by kickoff/freshness,
  enqueues collectors through framework (freshness+lock+quota gated) → OK
- FreshnessPolicy: per-category TTLs incl. PREMATCH phase; config-driven → OK
- QuotaManager: DB-backed ledger (`external_api_requests` + `quota_buckets`),
  P0–P3 priorities, reserve budget, degradation modes
  NORMAL/CONSERVE/CRITICAL/RESERVE_ONLY; provider headers parsed
  (API-Football + The Odds API formats) → OK
- Request coalescing: Redis lock manager with result publication;
  concurrent equivalent requests coalesce → OK
- Collectors: standings, team_stats, availability (UNKNOWN/KNOWN_NONE/
  KNOWN_PRESENT semantics), lineups (confirmed flag preserved; absent ≠
  empty), form_inputs (MOCK placeholder) → OK
- Odds: provider-independent typed interface; MockOddsProvider keyless;
  TheOddsApiProvider contract-tested normalization (h2h/double_chance/
  totals→ou_15|ou_25/btts), bounded retry, normalized ProviderError
  hierarchy, apiKey never logged; deterministic implied/no-vig math → OK
- Migration 0004: snapshots + odds + quota ledger tables; ORM aligned
  (DESC indexes); alembic check clean at head → OK
- job_attempts: worker executions record attempts (safe error class
  names only, no exception strings/secrets) → OK
- Status API: `/v1/fixtures/{id}/status` (freshness per category),
  `/v1/system/status`; read-only → OK
- Database-first UX: integration test proves GET fixtures/detail/status
  flow writes zero `external_api_requests` rows → OK
- Scope guard: no research/MatchContext/LLM/prediction/settlement/live → OK

# Verification (actually run)

- `uv run pytest -q -m "not integration"` → **233 passed**
- `make test-integration` equivalent → **38 passed**
  (incl. new M4 file: collectors persist/reuse, standings shared across
  fixtures = 1 ledger row per league, odds history immutable,
  quota buckets persisted, job_attempts recorded, status API 200/404,
  DB-first UX zero-provider-calls)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 82 source files** (strict)
- `alembic check` (integration `test_no_schema_drift_at_head`) → OK
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations

- FormInputsCollector is a MOCK-derived placeholder (completed-fixture
  history needs scores columns — deferred to M7 feature work).
- TheOddsApiProvider is contract-tested against the documented v4 shape;
  live odds verification intentionally NOT performed (no credentials;
  never blocks M4).
- Pre-match scan executes collectors inline in the scan task (deterministic);
  separate queue fan-out is a future optimization.

---

# Completion

- Status set to COMPLETE. Commit on `build/m4`. No merge to main.
- Stop after M4 for independent review. M5 not started.
