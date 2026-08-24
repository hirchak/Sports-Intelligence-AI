# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M4 — Automated Match Data Collection + Odds + Quota/Freshness  
**Review target branch:** `build/m4` (NOT merged to main)  
**Review target commit:** `d0ea666` — M4: automated collection, odds,
quota/freshness  
**Previous accepted state:** `main` = `7d23c9d` (M3 accepted via PR #5)  
**Review scope:** diff `main..build/m4`

---

# What changed since the last review (M3 → M4)

## 1. Scheduler (Celery Beat, deterministic)

- `workers/celery_app.py` builds a beat schedule only when
  `scheduler_enabled=True` (default False — quota-safe). Entries:
  - `discovery.morning` → task `sports.discover_fixtures`,
    crontab hour/minute from settings (default 09:00);
  - `discovery.refresh` → same task, default 13:00;
  - `pre_match.scan` → task `sports.pre_match_scan`, minute cron
    (default `*/15`), gated by its own `scheduler_pre_match_scan_enabled`
    toggle.
- Timezone resolution is Celery's `conf.timezone` = `APP_TIMEZONE`
  (Europe/Warsaw); DST-safe. Reuses M2 idempotency/version semantics
  for discovery identity.

## 2. Pre-match scanner

- `collectors/pre_match_scan.py`: pure-DB planner
  (`select_upcoming_fixtures` with aliased home/away teams,
  `decide_categories` MORNING vs PREMATCH by kickoff windows
  T-120/60/20 config, `plan_for_date`, `execute_plan`).
- `workers/tasks/pre_match.py`: Celery task wires runtime
  (Redis locks, QuotaManager, providers) and runs collectors through the
  framework; every collector re-checks freshness under the coalescing
  lock so duplicate dispatches short-circuit without provider calls.

## 3. Freshness policy

- `collectors/freshness.py`: frozen dataclass over Settings;
  per-category TTLs (standings/team stats/form/availability/lineups/odds)
  plus shorter PREMATCH TTLs (odds 30 min, availability 60 min).
  `None` captured_at is always stale (spec 14 §7).

## 4. QuotaManager + ledger

- `collectors/quota.py`: pure deterministic `decide()` (priority classes
  P0–P3, reserve budget, degradation modes NORMAL/CONSERVE/CRITICAL/
  RESERVE_ONLY), centralized header parser (API-Football + The Odds API),
  DB-backed `QuotaManager.acquire/record` persisting to
  `external_api_requests` + `quota_buckets`.
- **Framework ordering guarantee:** quota is acquired BEFORE any provider
  request in `run_collector`; a denied decision raises
  `QuotaUnavailableError` and never reaches the external API.

## 5. Request coalescing

- `collectors/locks.py`: Redis SET-NX locks with token-checked release
  (Lua), best-effort result publication + waiter polling with timeout
  fallback. Dataclass results are JSON-serialized safely
  (`asdict`) so waiters reuse the winner's fetch.

## 6. Collectors

- Standings (per league+season lock key), TeamStatistics
  (team+league+season), Availability (UNKNOWN / KNOWN_NONE / KNOWN_PRESENT
  semantics — provider silence ≠ healthy), Lineups (`confirmed` flag +
  players preserved; unavailable ≠ empty lineup), FormInputs (MOCK
  placeholder — completed-fixture history needs score columns, deferred),
  Odds (immutable snapshot sets + prices, implied/no-vig derived at
  persist time). All registered in `framework._REGISTRY`.

## 7. Odds provider boundary

- `providers/odds/base.py`: typed protocol (`OddsProvider`,
  `OddsProviderResult`, `OddsSelectionPrice`).
- `providers/odds/mock.py`: keyless deterministic MOCK (1X2, DC,
  OU 1.5/2.5, BTTS with coherent overrounds).
- `providers/odds/parse.py`: contract-tested normalizer for The Odds API
  v4 single-event payload (market whitelist, h2h→h2h_1x2 mapping by team
  names, totals split into ou_15/ou_25 by point, btts/double_chance
  selections, dedup, malformed-whitelisted-content raises
  ProviderResponseError).
- `providers/odds/factory.py`: `TheOddsApiProvider` with bounded retry
  (tenacity, retryable subset), normalized error hierarchy
  (401/403 auth, 429 rate limit, 5xx server, timeout/transport),
  apiKey never logged (httpx INFO logs silenced at provider init because
  the Odds API carries the key in the URL).

## 8. Data model / migration 0004

- Tables: standings_snapshots, team_statistics_snapshots,
  team_form_snapshots, availability_snapshots, lineup_snapshots,
  odds_snapshot_sets, odds_prices, external_api_requests, quota_buckets.
- UUID PKs, UTC timestamps, immutable snapshot families (append-only,
  unique capture constraints), FK cleanup rules, DESC composite indexes.
- ORM metadata aligned with migration (alembic check clean at head).

## 9. job_attempts closure

- `workers/utils.py::record_job_attempt`: one row per worker execution
  (attempt_number, started/finished, outcome, redacted error class name
  only — never exception strings or secrets). Wired into the discovery
  task success and failure paths.

## 10. Status API

- `GET /v1/fixtures/{id}/status`: per-category freshness
  (captured_at, age_seconds, fresh/stale/unknown), lineup availability,
  degraded mode, remaining quota.
- `GET /v1/system/status`: scheduler flag, degradation mode, remaining.
- Read-only: no collector/provider invocation from these endpoints.

---

# Verification (actually run on this machine)

- `uv run pytest -q -m "not integration"` → **233 passed**
- Integration suite (isolated `sports_intel_test` DB + Redis db15)
  → **38 passed**, incl. new `tests/integration/test_m4_collectors.py`:
  - collectors persist snapshots via real Postgres;
  - standings shared by two fixtures → exactly 1 ledger row per league
    (freshness hit → zero second provider call);
  - odds history immutable across runs (2 distinct snapshot sets);
  - quota record persists buckets + external requests;
  - job_attempts row recorded;
  - status API 200/404 + system endpoint;
  - **DB-first UX**: repeated GET fixtures/detail/status writes ZERO
    `external_api_requests` rows;
  - pre-match planner idempotent.
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 82 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations (documented, intentional)

1. FormInputsCollector is MOCK-derived; deterministic form from completed
   fixtures requires score columns (future milestone, feature work).
2. Live Odds API verification intentionally not performed (no local
   credentials required for acceptance; adapter is contract-tested).
3. Pre-match scan executes collectors inline (single task); queue fan-out
   per collector is a future optimization, not an M4 requirement.

# Scope guard respected

No web research, no MatchContext, no LLM, no prediction, no candidate
ranking, no settlement, no live in-play, no Hetzner, no Hermes.

---

# Suggested review order

1. `AGENTS.md`, this file, `docs/CURRENT_TASK.md`
2. Git diff `main..build/m4`
3. Specs: 08, 09, 10, 11, 14, 17
4. Key files:
   - `src/sports_intelligence/collectors/framework.py` (ordering:
     freshness → quota → lock/fetch → persist → ledger)
   - `src/sports_intelligence/collectors/quota.py`
   - `src/sports_intelligence/workers/celery_app.py`
   - `src/sports_intelligence/providers/odds/parse.py`
   - `tests/integration/test_m4_collectors.py`

# Next action after PASS

Merge `build/m4` into `main`, tag `v0.5-m4`. Only then start M5 with
explicit user approval.
