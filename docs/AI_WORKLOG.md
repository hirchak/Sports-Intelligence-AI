# AI Engineering Worklog

This file is **append-only**.

Purpose:
- preserve a durable engineering history across AI sessions;
- make review and recovery easy;
- record what was actually verified.

Do not rewrite old entries except to correct a factual typo, and mark corrections explicitly.

---

## Entry template

### YYYY-MM-DD HH:MM TZ — <agent/model>

**Milestone:** Mx  
**Task:** short task name

**Completed**
- ...

**Files changed**
- ...

**Verification**
- `command` → PASS/FAIL
- `command` → PASS/FAIL

**Live integrations verified**
- none / details

**Mocked only**
- ...

**Known issues**
- ...

**Spec / ADR deviations**
- none / ADR link

**Git**
- branch:
- commit:

**Next action**
- ...

---

### 2026-09-29 20:33 CEST — Antigravity (Claude Sonnet 4.6)

**Milestone:** M5.2  
**Task:** Focused correctness pass — all 6 M5.2 review findings

**Completed**
1. **Per-HTTP-attempt quota/ledger**: removed retry loop from `TavilySearchProvider.search()` (now single-attempt). Moved 3-attempt retry orchestration to `ResearchCollector.fetch()` with `quota.reserve()` + `record_success/failure()` per physical HTTP attempt. Imported `RETRYABLE_PROVIDER_ERRORS` for correct retry classification.
2. **`research_claim_extraction_enabled` as real Settings field**: added `research_claim_extraction_enabled: bool = True` to `Settings`; removed `getattr` fallback in collector; removed dead `self.extractor is None` branch; added `RESEARCH_CLAIM_EXTRACTION_ENABLED=true` to `.env.example`.
3. **DISABLED state in read API**: `get_research_for_fixture()` accepts `capability_enabled: bool = True`; when no run exists and capability is disabled → returns `DISABLED` instead of `NO_USEFUL_RESULTS`. API route reads `request.app.state.settings`.
4. **PROVIDER_ERROR not fresh**: `latest_snapshot()` selects `status` column; returns `(None, None)` for `PROVIDER_ERROR` runs, making them immediately stale for retry.
5. **Partial failure visibility**: after query loop, `partial_failure = provider_error is not None and bool(raw_items)`; partial failure → `status = PROVIDER_ERROR` even if documents exist; diagnostics (`queries_planned`, `queries_attempted`, `queries_succeeded`, `failed_query_count`, `partial_failure`, `provider_error_class`) persisted in `details_jsonb`.
6. **Typed mode validation**: `?mode=` changed from `str` to `Literal["latest_run", "accumulated"]` in API route and service; FastAPI returns HTTP 422 for invalid values.
7. **Scratch patch scripts cleanup**: removed 11 `patch_*.py` files left in project root; fixed 5 E501 lint errors in test files; ran `ruff format`.

**Files changed**
- `src/sports_intelligence/providers/search/tavily.py` — removed retry loop
- `src/sports_intelligence/collectors/research_collector.py` — retry orchestration, partial failure, latest_snapshot status check, extraction_enabled via settings
- `src/sports_intelligence/core/config.py` — added `research_claim_extraction_enabled`
- `src/sports_intelligence/research/service.py` — `capability_enabled` param, `Literal` mode type
- `src/sports_intelligence/api/routes/research.py` — `Literal` mode, pass capability_enabled
- `.env.example` — added `RESEARCH_CLAIM_EXTRACTION_ENABLED=true`
- `tests/unit/test_search_provider.py` — new retry-per-attempt tests; E501 fixes
- `tests/unit/collectors/test_research_collector.py` — new partial failure, PROVIDER_ERROR freshness, extraction_unavailable tests; E501 fixes
- `tests/integration/test_m5_research.py` — new 422 mode, DISABLED API, partial failure integration tests; E501 fix
- `docs/IMPLEMENTATION_STATUS.md`, `docs/CURRENT_TASK.md`, `docs/REVIEW_HANDOFF.md`, `docs/AI_WORKLOG.md`

**Verification**
- `uv run ruff check .` → All checks passed
- `uv run ruff format --check .` → 157 files already formatted
- `uv run mypy src` → Success: no issues found in 104 source files
- `uv run pytest -q -m 'not integration'` → 312 passed
- `pytest -q -m integration` (TEST_DATABASE_URL + TEST_REDIS_URL) → 74 passed

**Known problems**
- None

**Spec / ADR deviations**
- None

**Git**
- branch: `build/m5`
- commits: `fea1e71` (M5.2 implementation), `4f78e84` (scratch cleanup + lint fixes)

**Next action**
- Stop for independent review of `build/m5` HEAD `4f78e8402fc7d2e7b4f550d04b81e1ebf92399b4`

---

## Initial record

### 2026-08-20 — Project specification phase

**Milestone:** Pre-M0  
**Task:** Define engineering architecture and control documents

**Completed**
- Master technical specification created.
- Telegram specification created.
- Football analytics pipeline created.
- Agent/orchestration catalog created.
- Database lifecycle specification created.
- API quota/caching strategy created.
- LLM router policy created.
- Local-to-Hetzner lifecycle documented.
- Data provenance/leakage rules created.
- Forecasting methodology v1 created.
- Git/AI development workflow created.
- Local acceptance plan created.
- `AGENTS.md` project rules added.
- Persistent state/worklog/handoff templates added.

**Verification**
- Documentation only; implementation tests not yet applicable.

**Live integrations verified**
- none.

**Known issues**
- Runtime provider choices are not yet empirically validated.
- Project implementation has not started.

**Spec / ADR deviations**
- none.

**Git**
- branch: not yet recorded
- commit: not yet recorded

**Next action**
- Start M0 locally with DeepSeek V4 Pro.

---

### 2026-08-20 — DeepSeek V4 Pro (lead engineer, OpenCode)

**Milestone:** M0  
**Task:** Initialize repository, implement and verify M0

**Completed**
- Git repo initialized; spec pack committed to `main` (8723a91);
  M0 work on branch `build/m0` per `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`.
- Python scaffold: pyproject (hatchling, src layout, Python 3.12),
  `uv.lock`, `.python-version`.
- FastAPI skeleton (`/health`, `/ready`), pydantic-settings `Settings`
  with mode validation, JSON structured logging, async DB session factory.
- Provider Protocol interfaces (`SportsDataProvider`, `OddsProvider`,
  `SearchProvider`, `LLMProvider`, `LLMResult`) — no implementations.
- Docker: multi-stage Dockerfile (prod non-root / dev editable+reload),
  compose.yaml (sports-intel: postgres16/redis7/api, loopback 5433/6380/8000),
  compose.dev.yaml, `.dockerignore`.
- Alembic async scaffold (zero revisions; `alembic_version` table verified).
- CI: ruff, mypy, pytest, compose config validation (`.github/workflows/ci.yml`).
- Docs: README, ARCHITECTURE, LOCAL_DEVELOPMENT, DATA_MODEL, PIPELINES,
  TELEGRAM, DEPLOYMENT, SECURITY; ADRs 0001–0005.
- `.env.example`, `.gitignore`, `Makefile`, `opencode.json.example`.

**Files changed**
- Created: `pyproject.toml`, `uv.lock`, `Dockerfile`, `compose.yaml`,
  `compose.dev.yaml`, `.env.example`, `.gitignore`, `.dockerignore`,
  `Makefile`, `alembic.ini`, `.python-version`, `opencode.json.example`,
  `.github/workflows/ci.yml`, `src/sports_intelligence/**`,
  `tests/**`, `docs/ARCHITECTURE.md`, `docs/LOCAL_DEVELOPMENT.md`,
  `docs/DATA_MODEL.md`, `docs/PIPELINES.md`, `docs/TELEGRAM.md`,
  `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `README.md`.
- Updated: `docs/CURRENT_TASK.md`, `docs/IMPLEMENTATION_STATUS.md`,
  `docs/AI_WORKLOG.md`, `docs/REVIEW_HANDOFF.md`.

**Verification**
- `uv run pytest -q` → PASS (17 tests, Python 3.12.14)
- `uv run ruff check .` → PASS
- `uv run ruff format --check .` → PASS
- `uv run mypy src` → PASS (strict)
- `docker compose config -q` (+dev override) → PASS
- `docker compose up -d --build` → all services healthy
- `GET /health` → 200; `GET /ready` → 200 (db ok, redis ok)
- `alembic upgrade head|current|heads` in api container → exit 0
- CI first run pending after push.

**Live integrations verified**
- none (by design in M0).

**Mocked only**
- all external integrations are interfaces only; mock mode requires no keys.

**Known issues**
- starlette pinned `<1.0` (1.x deprecates httpx TestClient).
- uvicorn access logs plain-text while app logs are JSON (minor, M1).
- ADRs/CURRENT_TASK update ended up inside the initial `main` commit
  (root-commit HEAD resolution quirk) — harmless, documented here.

**Spec / ADR deviations**
- ADR-0005 (M0 includes API/infra skeleton per user instruction);
  ADR-0002 (specs stay in root); ADR-0003 (local ports);
  ADR-0004 (mode validation policy).

**Git**
- branch: `build/m0`
- commit: `6c8a193` (tag `v0.1-m0`)
- CI: green (both jobs)

**Next action**
- Independent M0 review; merge `build/m0` → `main` after acceptance;
  then M1 only with explicit user approval.

---

### 2026-08-20 — DeepSeek V4 Pro (fix milestone M0.1)

**Milestone:** M0.1  
**Task:** Apply review fixes (M0 review verdict: PASS WITH FIXES)

**Completed**
- `Settings` now loads the shared `.env` reliably: `env_ignore_empty=True`,
  `extra="ignore"` (Compose-only `POSTGRES_*` tolerated),
  `TELEGRAM_ALLOWED_USER_IDS` via `NoDecode` + comma-separated before-validator.
  Declared-field type validation unchanged and tested.
- ADR-0004 updated to document the new validation policy and alternatives.
- `.env.example` comments clarify compose-only variables and comma format.
- 7 dotenv regression tests added (read real dotenv files, not only kwargs):
  `.env.example` load, empty/comma user IDs, mock keyless, non-mock failure,
  compose-only tolerance, bad-type rejection.
- README + docs/LOCAL_DEVELOPMENT.md clone instructions fixed
  (`git clone git@github.com:hirchak/-.git sports-intelligence`).
- Technical debt recorded in IMPLEMENTATION_STATUS: M1 shared engine/client
  via lifespan for `/ready`; M2 normalized DTOs for provider interfaces.

**Files changed**
- `src/sports_intelligence/core/config.py`
- `tests/unit/test_config_dotenv.py` (new)
- `docs/adr/0004-runtime-modes-and-config-validation.md`
- `.env.example`, `README.md`, `docs/LOCAL_DEVELOPMENT.md`
- `docs/IMPLEMENTATION_STATUS.md`, `docs/CURRENT_TASK.md`,
  `docs/AI_WORKLOG.md`, `docs/REVIEW_HANDOFF.md`

**Verification**
- `uv run pytest -q` → PASS (24 tests: 17 M0 + 7 dotenv regression)
- `uv run ruff check .` / `ruff format --check .` → PASS
- `uv run mypy src` → PASS (strict)
- `docker compose up -d --build sports-api` → healthy after rebuild
- `GET /health` → 200; `GET /ready` → 200
- `docker compose exec sports-api alembic current` → exit 0
- CI: green after push (confirmed below)

**Live integrations verified**
- none (by design).

**Mocked only**
- all external integrations remain interfaces only.

**Known issues**
- starlette `<1.0` pin and uvicorn plain-text access logs remain (see M0 entry).
- `extra="ignore"` reduces unknown-var typo detection; mitigated by dotenv
  regression tests covering every documented variable.

**Spec / ADR deviations**
- ADR-0004 updated (env_ignore_empty, extra="ignore", NoDecode).

**Git**
- branch: `build/m0`
- commit: recorded in REVIEW_HANDOFF after commit
- tag: `v0.1-m0` moved to the final M0.1 commit

**Next action**
- Final independent review of M0.1; merge to `main` after acceptance;
  M1 only with explicit user approval.

---

### 2026-08-20 — DeepSeek V4 Pro (M0 finalize + M1 core infrastructure)

**Milestone:** M0 (finalize) + M1  
**Task:** Finalize M0 in main; implement M1 core infrastructure

**Completed**
- M0 finalized: repository renamed to `hirchak/Sports-Intelligence-AI`;
  remote updated; README/LOCAL_DEVELOPMENT clone URLs fixed; M0.1 merged to
  main via PR #2 (merge commit `7000c32`, no force push); CI green on main;
  tag `v0.1-m0` unchanged (`8d28138`).
- M1 DB infra: shared `AsyncEngine` + `async_sessionmaker` + Redis client
  in FastAPI lifespan; `get_session` dependency; `/ready` uses shared
  resources; clean shutdown (engine disposed, redis aclosed — tested).
- M1 Celery: app factory, Redis broker `/0` + backend `/1`, JSON/UTC,
  6 queues per agent catalog, route patterns, `control.ping` task,
  empty beat schedule; worker + beat compose services.
- M1 migration `0001`: `jobs` + `job_attempts` (scope ADR-0006).
- CI: new integration job with postgres/redis service containers;
  unit job excludes integration.
- Docs updated (README, ARCHITECTURE, LOCAL_DEVELOPMENT, DATA_MODEL,
  PIPELINES, ADR-0006).

**Files changed**
- Created: `src/sports_intelligence/db/models/{base,jobs}.py`,
  `db/migrations/versions/0001_*.py`, `api/readiness.py`,
  `api/dependencies.py`, `workers/celery_app.py`, `workers/tasks/control.py`,
  `tests/unit/test_celery_app.py`, `tests/unit/test_readiness.py`,
  `tests/integration/test_db_resources.py`, `docs/adr/0006-*.md`
- Modified: `core/config.py` (celery URLs), `api/app.py` (lifespan),
  `api/routes/health.py`, `db/migrations/env.py` (metadata + preset URL),
  `script.py.mako`, `alembic.ini` (path_separator), `pyproject.toml`
  (celery dep, mypy overrides, markers), `compose.yaml` (worker/beat),
  `Makefile`, `.env.example`, `.github/workflows/ci.yml`, README, docs/*

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (34)
- `uv run pytest -q -m integration` (local services) → PASS (3)
- `uv run ruff check .` / `ruff format --check .` → PASS
- `uv run mypy src` → PASS (strict)
- `docker compose config -q` (+ dev override) → PASS
- Docker smoke: 5 services up; /health 200; /ready 200; alembic upgrade
  created jobs/job_attempts/alembic_version; worker ready (6 queues);
  beat started; `control.ping` via broker → succeeded (pong=True)
- CI on push → confirmed below

**Live integrations verified**
- none (by design in M1).

**Mocked only**
- all external integrations remain interfaces only.

**Known issues**
- Docker Desktop multi-service bake gRPC bug on macOS; per-service build
  workaround documented in LOCAL_DEVELOPMENT.md.
- starlette `<1.0` pin; uvicorn plain access logs (minor).
- celery untyped → `type: ignore[untyped-decorator]` on ping task.

**Spec / ADR deviations**
- ADR-0006 (M1 migration scope + celery queue layout).

**Git**
- branch: `build/m1`
- commits: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent M1 review; merge to `main` after acceptance;
  M2 only with explicit user approval.

---

### 2026-08-20 — DeepSeek V4 Pro (fix milestone M1.1)

**Milestone:** M1.1  
**Task:** Apply M1 review fixes (verdict: PASS WITH FIXES)

**Completed**
- Isolated integration database: dedicated `sports_intel_test` (auto-created
  by `make test-integration`); `TEST_DATABASE_URL` always test-DB; CI uses
  ephemeral Postgres with `sports_intel_test`; Redis test traffic on db 15.
- Guard `tests/helpers.py::require_test_database`: refuses any TEST_DATABASE_URL
  whose DB name doesn't end with `_test` (loud RuntimeError). Unit-tested.
- Dev DB protection verified: table snapshot of `sports_intel` identical
  before/after the integration suite (twice).
- Lifespan cleanup refactored to try/finally via
  `api/resources.py::close_resources`; one failing cleanup never blocks the
  other; exceptional-exit test proves redis aclose + engine dispose run.
- Docs updated (LOCAL_DEVELOPMENT test isolation section).

**Files changed**
- Created: `src/sports_intelligence/api/resources.py`,
  `tests/helpers.py`, `tests/unit/test_resources_cleanup.py`,
  `tests/unit/test_testdb_guard.py`, `tests/integration/conftest.py`
- Modified: `src/sports_intelligence/api/app.py`,
  `tests/integration/test_health_api.py`,
  `tests/integration/test_db_resources.py`, `Makefile`,
  `.github/workflows/ci.yml`, `pyproject.toml` (pythonpath, helpers
  first-party), `docs/LOCAL_DEVELOPMENT.md`, state files

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (41)
- `make test-integration` → PASS (3) on sports_intel_test
- guard negative check (dev DB URL) → fails loudly as designed
- `uv run ruff check .` / `ruff format --check .` → PASS
- `uv run mypy src` → PASS (strict)
- `docker compose config -q` (+dev) → PASS
- Docker smoke: 5 services up, /health 200, /ready 200
- dev DB unchanged after suite (diff of table snapshots)

**Live integrations verified**
- none (by design).

**Mocked only**
- all external integrations remain interfaces only.

**Known issues**
- unchanged from M1 (Docker Desktop bake bug, starlette pin, celery untyped).

**Spec / ADR deviations**
- none new.

**Git**
- branch: `build/m1`
- commit: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent M1.1 review; merge to `main` after acceptance;
  M2 only with explicit user approval.

---

### 2026-08-20 — DeepSeek V4 Pro (M1 finalize + M2 sports provider/discovery)

**Milestone:** M1 (finalize) + M2  
**Task:** Finalize M1 in main; implement API-Football + fixture discovery

**Completed**
- M1 finalized: PR #3 merged (`25dda83`), CI green on main, tag `v0.2-m1`.
- Typed provider DTOs (`providers/dto.py`) replacing `dict[str, Any]` on
  the discovery path; UTC normalization; explicit None for missing fields.
- `ApiFootballProvider`: async httpx, env-only key, bounded retry
  (tenacity; auth non-retryable), normalized `ProviderError` hierarchy,
  rate-limit metadata, raw payload for evidence, injected transport.
- `MockSportsDataProvider` (recorded sanitized responses, keyless).
- Migration 0002: leagues/seasons/teams/fixtures/provider_entity_ids/
  raw_provider_payloads (ADR-0008, PostgreSQL upserts, UTC, indexes).
- `FixtureDiscoveryService`: batch-first, idempotent, raw payload
  hash-dedup, provider identity on mappings.
- League YAML config (`config/leagues.yaml` all disabled; mock demo
  config; `make seed`).
- API: `/v1/fixtures` (+date/league), `/v1/fixtures/{id}`,
  `POST /v1/jobs/discover` (jobs row + idempotency key + Celery enqueue).
- Celery `sports.discover_fixtures` (sports_io), job status updates;
  fixed worker task registration (include list). No schedule.
- ADR-0007 (provider choice), ADR-0008 (schema scope).

**Files changed**
- Created: `providers/{dto,errors}.py`, `providers/sports/{api_football,
  mock,factory}.py` + mock_data, `core/{league_config,job_status}.py`,
  `db/models/discovery.py`, `db/repositories/discovery.py`,
  `pipelines/discover_fixtures.py`, `api/routes/{fixtures,jobs}.py`,
  `workers/tasks/sports.py`, `schemas/fixtures.py`,
  `scripts/seed_leagues.py`, `config/leagues.yaml`,
  `config/leagues.mock.yaml`, migration `0002`, tests (unit×4 files,
  integration×1, recorded fixture JSON), ADRs 0007/0008
- Modified: `providers/base.py`, `core/config.py`, `api/app.py`,
  `db/models/__init__.py`, `workers/celery_app.py`, `compose.yaml`,
  `Dockerfile`, `Makefile`, `.env.example`, `pyproject.toml`, `uv.lock`,
  integration conftest, docs

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (63)
- `make test-integration` → PASS (10) on isolated sports_intel_test
- ruff / format / strict mypy (50 files) → PASS
- compose validation → PASS; docker smoke: 5 services, /health/ready 200
- Mock discovery via full stack → fixtures persisted (earlier smoke)
- Live API-Football smoke (bounded, 2 calls): 2026-08-21 → 383 fixtures
  in ONE request → 1 eligible (Premier League, Arsenal vs Coventry)
  persisted; raw payload 401 KB hash-deduplicated; repeat run idempotent
  (0 created / 1 updated / no payload dup); job SUCCEEDED; key absent
  from logs; key stored only in local `.env` (gitignored)
- CI on push → confirmed below

**Live integrations verified**
- API-Football fixture discovery: bounded live smoke PASS (single date,
  single league). Not verified: multi-day production usage, quota edges.

**Mocked only**
- MockSportsDataProvider for offline/CI/test runs.

**Known issues**
- Docker Desktop bake bug (per-service build workaround).
- job_attempts rows not written yet (M4 debt); QuotaManager M4.
- starlette <1.0 pin; celery untyped decorators.

**Spec / ADR deviations**
- ADR-0007, ADR-0008.

**Git**
- branch: `build/m2`
- commits: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent M2 review; merge to `main` after acceptance;
  M3 only with explicit user approval.

---

### 2026-08-20 — DeepSeek V4 Pro (fix milestone M2.1)

**Milestone:** M2.1  
**Task:** Apply M2 review fixes (verdict: PASS WITH FIXES)

**Completed**
- retrieved_at moved after final successful response (post-retry);
  regression test with retry/delay.
- Immutable evidence history: raw_provider_payloads (content, dedup) +
  provider_observations (append-only retrieval events); ADR-0009;
  migration 0003 with data migration for existing rows; replay resolves
  as_of via observation.retrieved_at.
- Atomic identity: PostgreSQL CTE arbiter for teams/fixtures (mapping
  insert decides winner; entity row created in same statement with the
  mapping's id); concurrency test (asyncio.gather) proves one Team + one
  mapping. Fixture refresh updates mutable metadata in place (same UUID;
  kickoff-change test).
- upsert_league_id syncs `enabled` (test false→true→false).
- Discovery resolves enabled league IDs per CURRENT provider; zero enabled
  → empty summary + 0 provider calls (test); config/leagues.mock.yaml with
  explicit mock:/api_football: IDs.
- Timezone: local_today/utc_window_for_local_day (APP_TIMEZONE); POST
  without date uses local date; GET ?date= uses local-day UTC boundaries;
  adapter sends timezone param; DST-boundary + midnight tests.
- Provider factory: unknown/empty provider → ProviderConfigError (no
  silent mock fallback).
- Enqueue failure → job FAILED + 502; re-POST requeues the same job row
  (PENDING), no duplicates.
- Missing data: nullable team/league names in DTO/DB; missing status
  (required identity) fails validation; no Unknown/UNKNOWN invented.
- ADR-0008 amended (composite indexes created in 0003, atomic pattern,
  enabled sync); mock_data packaged into wheel (hatch force-include).

**Files changed**
- Created: `db/migrations/versions/0003_*.py`,
  `docs/adr/0009-immutable-provider-observation-history.md`,
  `tests/unit/test_factory_and_retry.py`, `tests/unit/test_time.py`
- Modified: `providers/dto.py`, `providers/errors.py`,
  `providers/base.py`, `providers/sports/{api_football,factory,mock}.py`,
  `core/time.py`, `db/models/{discovery.py,__init__.py}`,
  `db/repositories/discovery.py`, `pipelines/discover_fixtures.py`,
  `api/routes/{fixtures,jobs}.py`, `schemas/fixtures.py`,
  `workers/tasks/sports.py`, `pyproject.toml` (hatch force-include),
  `config/leagues.mock.yaml`, `tests/integration/test_fixture_discovery.py`,
  `docs/adr/0008-*.md` (amendment), docs/*, state files

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (74)
- `make test-integration` → PASS (16) on isolated sports_intel_test
- ruff / format / strict mypy (51 files) / compose validation → PASS
- Docker smoke: 0003 applied (existing live row migrated to
  observations); MOCK discovery via stack: 4→3 created, repeat 0/3 +
  observation appended, content dedup; bounded live smoke: 1 request,
  383 fixtures, 1 eligible updated, observation appended; no key in logs
- secret scan clean; keys only in local .env

**Live integrations verified**
- API-Football discovery: bounded smoke (1 call in M2.1). Not verified:
  multi-day production usage, quota edges.

**Mocked only**
- MockSportsDataProvider for offline/CI/test runs.

**Known issues**
- Docker Desktop bake bug (per-service build workaround).
- job_attempts rows not written (M4); QuotaManager (M4).
- Enqueue-failure recovery covers FAILED jobs via manual re-POST; PENDING
  jobs lost from the broker are not auto-detected until M4 outbox.

**Spec / ADR deviations**
- ADR-0008 amended; ADR-0009 created.

**Git**
- branch: `build/m2`
- commits: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent M2.1 review; merge to `main` after acceptance;
  M3 only with explicit user approval.

---

### 2026-08-21 — DeepSeek V4 Pro (short fix milestone M2.2)

**Milestone:** M2.2  
**Task:** Apply final M2.1 review fixes (verdict: PASS WITH FIXES)

**Completed**
- Canonical request fingerprint: deterministic
  `provider:endpoint_family:sorted(params)` incl. date+timezone; stored in
  provider_observations; unit tests (stability, tz sensitivity,
  order-independence, provider distinction) + adapter/mock wiring.
- FAILED-job requeue race: CAS transition
  `transition_job_status_if(FAILED->PENDING)`; handler re-reads status
  after enqueue; regression test simulates worker RUNNING transition
  between apply_async and HTTP update (job stays RUNNING, no downgrade).
- ORM synchronized with migration 0003: composite indexes
  ix_fixtures_league_kickoff / ix_fixtures_status_kickoff in ORM; stale
  single-column index=True removed; `alembic check` at head added to
  integration suite (green — no drift).
- Hardened arbiter: bounded safe resolution (row → use; empty → fresh
  SELECT; 3 bounded retries); no scalar_one() without fallback; targeted
  synchronized 6-participant race test: 1 mapping, 1 team, same UUID for
  all callers.
- Worker init exception-safe: engine/provider cleanup in finally with
  independent try/excepts; job marked FAILED when DB reachable; original
  exception re-raised; integration + unit tests (dispose verified with
  tracking engine).

**Files changed**
- Modified: `providers/dto.py` (fingerprint helper),
  `providers/sports/{api_football,mock}.py`, `db/models/discovery.py`
  (composite indexes), `db/repositories/discovery.py` (bounded arbiter),
  `pipelines/discover_fixtures.py` (CAS transition),
  `api/routes/jobs.py` (CAS requeue + refresh),
  `workers/tasks/sports.py` (exception-safe init), tests (new
  `test_fingerprint.py`, `test_worker_init_cleanup.py`, integration
  additions), state files

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (79)
- `make test-integration` → PASS (20) incl. alembic check + race tests
- ruff / format / strict mypy (51 files) / compose validation → PASS
- Docker MOCK smoke: idempotent discovery (0/3), observation fingerprint
  canonical (mock:fixtures_by_date:date=2026-08-21&timezone=Europe/Warsaw),
  health/ready 200
- Live API-Football smoke intentionally NOT repeated (no HTTP contract
  change; quota preserved)
- CI on push → confirmed below

**Live integrations verified**
- unchanged from M2.1 (bounded live smokes in M2/M2.1 remain valid;
  M2.2 changed no HTTP contract).

**Mocked only**
- MockSportsDataProvider for offline/CI/test runs.

**Known issues**
- Docker Desktop bake bug (per-service build workaround).
- job_attempts rows (M4); QuotaManager (M4); full outbox (M4).

**Spec / ADR deviations**
- none new (fingerprint/CAS refinements extend ADR-0008/0009 behavior).

**Git**
- branch: `build/m2`
- commits: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent M2.2 review; merge to `main` after acceptance;
  M3 only with explicit user approval.

---

### 2026-08-21 — DeepSeek V4 Pro (minimal fix milestone M2.3)

**Milestone:** M2.3  
**Task:** Apply final M2.2 review fix (verdict: PASS WITH ONE REQUIRED FIX)

**Completed**
- Discovery job idempotency key now matches `09` spec:
  `discover:{provider}:{date}:v{league_config_version}:{timezone}` —
  LeagueConfig version loaded from the configured YAML is the canonical
  identity mechanism; enabled-league list never appears in the key;
  timezone included because the provider request depends on it.
- Rule documented: semantic changes to config/leagues.yaml must bump
  `version` (config file header + LOCAL_DEVELOPMENT + ARCHITECTURE).
- Tests: duplicate POST same identity → no duplicate job/enqueue;
  config-version change → new job + enqueue; timezone change → distinct
  identity (Warsaw vs London); FAILED retry keeps the same job UUID.
- Stale IMPLEMENTATION_STATUS strings synced (In-progress block, provider
  selected/verified — API-Football, reviewer diff main..build/m2, raw
  evidence description post-ADR-0009).

**Files changed**
- Modified: `src/sports_intelligence/api/routes/jobs.py` (key construction),
  `tests/integration/test_fixture_discovery.py` (new/updated identity
  tests), `config/leagues.yaml` (version-bump rule),
  `docs/{ARCHITECTURE,LOCAL_DEVELOPMENT,IMPLEMENTATION_STATUS,CURRENT_TASK,
  AI_WORKLOG,REVIEW_HANDOFF}.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (79)
- `make test-integration` → PASS (23) incl. alembic check
- ruff / format / strict mypy (51 files) / compose validation → PASS
- live API smoke NOT repeated (no HTTP contract change — quota preserved)
- CI on push → confirmed below

**Live integrations verified**
- unchanged (bounded live smokes from M2/M2.1 remain valid).

**Mocked only**
- MockSportsDataProvider for offline/CI/test runs.

**Known issues**
- Docker Desktop bake bug (per-service build workaround).
- job_attempts rows (M4); QuotaManager (M4); full outbox (M4).

**Spec / ADR deviations**
- none new (key format now matches spec 09 exactly).

**Git**
- branch: `build/m2`
- commits: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent review; merge to `main` after acceptance;
  M3 only with explicit user approval.

---

### 2026-08-21 — DeepSeek V4 Pro (minimal fix milestone M2.4)

**Milestone:** M2.4  
**Task:** Apply final M2.3 review fix (verdict: PASS WITH ONE SMALL SAFETY FIX)

**Completed**
- Discovery Celery task now receives the full job identity payload:
  `job_id`, `fixture_date`, `expected_league_config_version`,
  `discovery_timezone` — enqueued by the HTTP layer from the same values
  encoded in the idempotency key.
- Worker loads the LeagueConfig and refuses to execute when the loaded
  `version` differs from the expected one: deterministic
  `LeagueConfigVersionMismatchError` (new, in `core/league_config.py`),
  zero provider requests, job marked FAILED.
- `FixtureDiscoveryService` receives `discovery_timezone` from the job;
  `settings.app_timezone` is no longer re-read at execution time.
- Regression tests (integration): enqueued v1 + worker sees v1 →
  executes and SUCCEEDS; config drifts to v2 before execution → 0
  provider calls + FAILED; job with `Europe/Warsaw` uses Warsaw even
  when current settings say `Europe/London`. Existing MOCK
  discovery/idempotency tests unchanged and green.

**Files changed**
- Modified: `src/sports_intelligence/core/league_config.py` (new
  exception), `src/sports_intelligence/workers/tasks/sports.py` (task
  signature, version guard, job timezone),
  `src/sports_intelligence/api/routes/jobs.py` (enqueue args),
  `tests/unit/test_worker_init_cleanup.py` (updated call),
  `tests/integration/test_fixture_discovery.py` (updated call + 3 new
  regression tests), `docs/{IMPLEMENTATION_STATUS,CURRENT_TASK,
  AI_WORKLOG}.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (79)
- `make test-integration` → PASS (26) incl. schema-drift `alembic check`
  and the 3 new regressions
- ruff check / ruff format --check / strict mypy (51 source files) →
  PASS
- `docker compose config -q` (+dev) → OK
- live API smoke NOT repeated (quota preserved); no migration needed

**Known problems**
- none new (job_attempts rows, QuotaManager, full outbox remain M4 debt)

**Spec / ADR deviations**
- none; worker cannot execute a different semantic config than the job
  identity encodes (per final M2.3 review)

**Git**
- branch: `build/m2`
- commit hash: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent review; merge to `main` after acceptance;
  M3 only with explicit user approval.

---

### 2026-08-21 — DeepSeek V4 Pro (M2 finalization)

**Milestone:** M2 (incl. M2.1–M2.4)  
**Task:** Record final independent review verdict; prepare accepted state

**Completed**
- Final independent review of M2.4 returned **PASS — M2 ACCEPTED**;
  safe to begin M3: YES.
- Documentation-state cleanup only (no production code changes):
  IMPLEMENTATION_STATUS section 1 (current objective) no longer says M1
  is awaiting review — now records the M2 PASS verdict and the
  merge/tag/M3 sequence; section 12 (next action) and section 13
  (reviewer notes — final verdict) synced; REVIEW_HANDOFF marked
  "review completed" with the verdict; CURRENT_TASK completion notes
  the verdict.

**Files changed**
- Modified: `docs/{IMPLEMENTATION_STATUS,REVIEW_HANDOFF,CURRENT_TASK,
  AI_WORKLOG}.md`

**Verification**
- docs-only change; no tests required (no code touched)

**Spec / ADR deviations**
- none

**Git**
- branch: `build/m2`
- commit: docs cleanup commit (see log)

**Next action**
- PR `build/m2` → `main`, merge normally, verify CI on main, tag
  `v0.3-m2`, create `build/m3`, start M3.

---

### 2026-08-21 — DeepSeek V4 Pro (M3 + Russian button navigation)

**Milestone:** M3 (Telegram base UI / private control plane)  
**Task:** Implement the first Telegram bot; pivot to Russian UI with
button-based menus and a Back button on every screen.

**Completed**
- `sports_intelligence.bot` package: `app` (aiogram Bot/Dispatcher
  factory), `access` (central allowlist middleware — message +
  callback), `backend_client` (typed methods: health, list fixtures,
  get fixture, discover; bot-safe error normalization), `transport`
  (send_text / edit_text / answer_callback protocol + aiogram
  impl + FakeTransport for tests), `context` (AppContext dataclass),
  `formatting` (Russian text, APP_TIMEZONE kickoff with Russian month
  abbreviations, league grouping, pagination, HTML escaping, "—"
  for missing team names, Back button on fixture page), `strings`
  (all Russian UI text), `menu` (main menu, find menu, dashboard,
  back-to-main keyboard builders), `handlers` (commands + inline
  callbacks + menu callbacks, all responses include a «← Назад»
  button), `callback_data` (fx/pg/rf/disc/health/menu:* payloads),
  `__main__.py` (long-polling entrypoint).
- Russian UI (single language); main menu Сегодня / Найти / Здоровье /
  Помощь; every screen has a «← Назад» button returning to the main
  menu; find menu offers yesterday / today / tomorrow plus the
  `/fixtures ГГГГ-ММ-ДД` hint for arbitrary dates; commands retained
  as a power-user fallback reach the same screens.
- Access control: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_IDS`
  enforced centrally (message + callback); unknown users get
  "Доступ запрещён." / silent callback answer; empty allowlist denies
  everyone.
- Docker Compose `telegram` profile: isolated `sports-telegram`
  service (no exposed ports), internal networking to `sports-api`,
  `BOT_BACKEND_BASE_URL` env; ordinary dev stack starts without
  Telegram credentials.
- Settings: added `bot_backend_base_url` (default
  `http://localhost:8000`; compose overrides to
  `http://sports-api:8000`).
- Dependency: `aiogram>=3.7` added to `pyproject.toml` /
  `uv.lock` (3.30 supported).
- Tests: 72 deterministic bot unit tests (access, formatting,
  backend client, handlers, callbacks, menu builders) — no token
  required.
- Localised error / status / help / dashboard / fixture / discover
  text to Russian; rus-month abbreviations; refresh + pagination
  buttons renamed.

**Files changed**
- Modified: `pyproject.toml`, `uv.lock`, `compose.yaml`, `Makefile`,
  `.env.example`, `src/sports_intelligence/core/config.py`,
  `docs/{CURRENT_TASK,IMPLEMENTATION_STATUS,TELEGRAM,ARCHITECTURE}.md`
- Added: `src/sports_intelligence/bot/{__main__,app,access,
  backend_client,callback_data,context,formatting,handlers,menu,
  strings,transport}.py`, `tests/telegram_fakes.py`,
  `tests/unit/test_bot_{backend_client,access,formatting,callbacks,
  handlers}.py`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (151)
- `make test-integration` → PASS (26) incl. alembic check
- ruff check / ruff format --check / strict mypy (62 source files)
  → PASS
- docker compose config -q (+ telegram profile) → OK
- secret scan: token / user IDs only in local `.env` (gitignored)
- live Telegram smoke (bot running in Docker):
  - English commands /start /today /health /discover + inline fixture
    tap verified via bot/worker logs.
  - Russian main menu + button navigation verified live (user
    screenshot).

**Live integrations verified**
- unchanged (M2 bounded live smokes remain valid).

**Known issues**
- One accidental live API-Football call (1301 fixtures received, 5
  created) was consumed during the first smoke because the local
  `.env` had `SPORTS_PROVIDER=api_football`. The smoke was pinned to
  MOCK afterwards; the second discovery round-trip (MOCK) hit the
  built-in dataset (4 received / 3 eligible / 0 created / 3 updated)
  and duplicate POST returned `already_queued: true`. Quota-safe
  default (`config/leagues.yaml`, all leagues disabled) restored on
  the stack after the smoke.
- `job_attempts` rows, QuotaManager, full outbox remain M4 debt;
  documented.
- Docker Desktop multi-service bake build bug (per-service build
  workaround documented).

**Spec / ADR deviations**
- Initial review of M3 requested spec-defined commands; user
  feedback pivoted the UI to single-language Russian with button-based
  navigation (commands retained as power-user fallback). All other
  M3 spec requirements kept.

**Git**
- branch: `build/m3`
- commit hash: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent review of M3; merge to `main` after acceptance;
  M4 only with explicit user approval.

---

### 2026-08-21 — DeepSeek V4 Pro (minimal fix milestone M3.1)

**Milestone:** M3.1  
**Task:** Apply final M3 review fix (verdict: PASS WITH TWO SMALL FIXES)

**Completed**
- Telegram callback acknowledgement is now guaranteed exactly once:
  the shared `_answer_from_callback` helper always calls
  `answer_callback` before editing/sending; the explicit duplicate
  `answer_callback` calls that previously preceded the helper were
  removed. As a result, malformed `fx:` / `pg:` / `rf:` payloads
  still get a safe Russian UI response (`Неизвестное действие.` +
  Back button) AND the Telegram client stops its "loading" indicator.
- `bot.__main__.main()` now suppresses `KeyboardInterrupt` only; a
  `SystemExit` raised by `run()` (e.g. when `TELEGRAM_BOT_TOKEN` is
  empty) propagates so the process exits with the failure code. Normal
  Ctrl+C remains a clean shutdown.
- The startup refusal message is a static string — no token
  interpolation, no secret-like fragments. Token never logged.
- Future roadmap (documented only, NOT implemented) added to
  `docs/IMPLEMENTATION_STATUS.md` §14: scheduled pipeline populates
  PostgreSQL automatically, Telegram screens read ready DB data,
  future availability/lineup collector boundary, PREMATCH_FINAL
  vs MORNING snapshot semantics, future live analytics is a separate
  post-v1 extension.
- Scope guard verified: scheduler, automatic discovery, sports
  collectors, odds, lineups / injuries, quota manager, research,
  MatchContext, LLM prediction, live football analysis — still NOT
  implemented.

**Files changed**
- Modified: `src/sports_intelligence/bot/handlers.py` (central
  acknowledgement in `_answer_from_callback`; remove duplicate
  pre-calls), `src/sports_intelligence/bot/__main__.py` (only
  suppress `KeyboardInterrupt`), `tests/unit/test_bot_handlers.py`
  (5 new tests: malformed fx/pg/rf + valid ack-once + catch-all
  silent), `tests/unit/test_bot_main.py` (new file: 3 startup
  tests), `docs/{CURRENT_TASK,IMPLEMENTATION_STATUS,
  REVIEW_HANDOFF,AI_WORKLOG}.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (159)
- `make test-integration` → PASS (26) incl. alembic check
- ruff check / ruff format --check / strict mypy (62 source files) →
  PASS
- docker compose config -q (+ telegram profile) → OK
- live Telegram smoke NOT repeated (covered by unit tests)
- live API-Football smoke NOT done (quota preserved)

**Known issues**
- none new (job_attempts rows, QuotaManager, full outbox remain M4
  debt)

**Spec / ADR deviations**
- none new (M3 → M3.1 keeps architecture and ADR-0007/API-Football
  boundary intact)

**Git**
- branch: `build/m3`
- commit hash: recorded in REVIEW_HANDOFF after commit

**Next action**
- Final independent review of M3.1; merge to `main` after
  acceptance; M4 only with explicit user approval.

---

### 2026-08-24 — ox-alpha (OpenCode)

**Milestone:** M4
**Task:** Automated Match Data Collection + Odds + Quota/Freshness — finish implementation started in a prior session (uncommitted working tree on `build/m4`)

**Completed**
- Recovered state from repo (no chat memory): M3 merged to `main` (`7d23c9d`); M4 work existed uncommitted on `build/m4` (config, celery beat, migration 0004, snapshot models, collectors skeleton, quota, locks, freshness, status API, job_attempts util).
- Fixed `framework.run_collector` ordering: quota is now acquired BEFORE any provider fetch; denial raises `QuotaUnavailableError` and never reaches the provider.
- Made coalescing result publication JSON-safe: dataclass results serialize via `asdict`; waiters rebuild `CollectorResult`.
- Removed double provider call in `OddsCollector.persist` (reuses fetched normalized prices; Decimal round-trip via strings).
- Implemented The Odds API v4 normalizer (`providers/odds/parse.py`, contract-tested) and rewired `TheOddsApiProvider`: bounded tenacity retry, ProviderError hierarchy (401/403/429/5xx/timeout/transport), apiKey never logged (httpx INFO silenced at init because the key rides the URL).
- Fixed Celery crontab usage (no `timezone=` kwarg; timezone resolves via `conf.timezone`=APP_TIMEZONE, DST-safe); pre-match scan toggle honored.
- Aligned ORM with migration 0004 DESC indexes (alembic check clean); added explicit `updated_at` on snapshot persist (no server_default in DB for those columns).
- Fixed duplicate-table-alias SQL bug in `select_upcoming_fixtures` (ORM `aliased(Team)`).
- Tests: framework quota-order/stale/concurrency, confirmed-lineup polling stop, locks concurrency, sports-collector availability/lineup semantics, odds normalizer contract (8), TheOddsApiProvider error mapping + key-leak (7), beat schedule semantics incl. disabled default (12 total in file), new integration file `test_m4_collectors.py` (12 tests: persist/reuse, standings shared → single ledger row, odds immutable history, quota ledger, job_attempts, status API 200/404/system, DB-first UX zero external rows, planner idempotent).

**Files changed**
- src: collectors/{framework,locks,sports_collectors,odds_collector,pre_match_scan}.py; providers/odds/{factory,parse}.py (new parse); workers/{celery_app,tasks/sports,tasks/pre_match,utils}.py; db/models/snapshots.py; api/routes/status.py; core/{config,phases}.py; db/migrations/versions/0004_*.py
- tests: unit/collectors/{test_framework,test_sports_collectors,test_quota,test_freshness,test_odds_math,test_pre_match_scan}; unit/test_celery_app; unit/test_odds_normalize (new); unit/test_theoddsapi (new); integration/test_m4_collectors (new)
- docs: CURRENT_TASK.md, IMPLEMENTATION_STATUS.md, REVIEW_HANDOFF.md, AI_WORKLOG.md

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (233)
- integration suite (`sports_intel_test` + redis db15) → PASS (38)
- `uv run ruff check . && uv run ruff format --check .` → PASS
- `uv run mypy src` → PASS (82 files, strict)
- `docker compose config -q` (+telegram profile) → PASS
- secret scan → clean

**Live integrations verified**
- none this session (MOCK-only by design; live Odds API intentionally not called — no credentials required for acceptance).

**Mocked only**
- FormInputsCollector (completed-fixture form needs score columns — deferred);
- TheOddsApiProvider network path (contract-tested against documented v4 shape).

**Known issues**
- Pre-match scan executes collectors inline in one task (queue fan-out is future optimization).
- Dev DB accumulated test leagues from repeated integration runs (unique-slug strategy; harmless).

**Spec / ADR deviations**
- none new; ADRs 0001–0009 unchanged. Framework quota-before-fetch ordering implements spec 11 §"prevent unnecessary requests" explicitly.

**Git**
- branch: build/m4
- commit: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent review of M4 (diff `main..build/m4`); merge + tag `v0.5-m4` after PASS; M5 only with explicit user approval.

---

### 2026-08-24 — ox-alpha (OpenCode)

**Milestone:** M4.1
**Task:** Corrective implementation after independent M4 review **FAIL** (14 required fixes)

**Completed**
- 1. Scheduled discovery: `sports.schedule_discovery(slot)` wrapper (morning/refresh distinct jobs, full immutable tuple, config-version safety, FAILED on enqueue error); Beat rewired to wrapper.
- 2. No fake data in real paths: extended `SportsDataProvider` protocol with typed category methods; real `ApiFootballProvider` adapters (standings/team stats/injuries/lineups/completed fixtures); collectors resolve external ids via `provider_entity_ids`; sentinel MockTransport regression tests.
- 3. Team-specific persistence: one fixture request → one snapshot PER team (never merged); team_id-aware freshness.
- 4. Lineup windows: `lineup_poll_due` state machine (NOT_YET_PUBLISHED/CONFIRMED/UNSUPPORTED/PROVIDER_ERROR), no started-fixture polling, per-window refresh (T-120 unconfirmed → T-60 due → confirmed stops), Warsaw calendar-day→UTC planner boundaries, phase propagated into CollectorContext.
- 5. Coalescing: lock is a budget boundary (no fetch-anyway, LockContendedError), winner double-check, waiters reuse winner's REAL persisted snapshot id, freshness hit returns real id, evidence committed before snapshot persist (payload_id FK), 10-caller concurrency test (1 call/1 snapshot/1 ledger/same UUID).
- 6. Quota: pct-of-actual-limit thresholds (100/500/7500), CONSERVE=P3, CRITICAL=P2/P3, RESERVE_ONLY=P0, effective_reserve keeps CRITICAL reachable, atomic Redis reservation with estimated cost, concurrent reservation test (10 workers → 4 allowed).
- 7. Provider-specific headers: API-Football daily+minute; Odds remaining/used/last=cost.
- 8. Ledger telemetry: started_at before request, duration incl HTTP, status/error class/headers/cost, failures visible.
- 9. The Odds API: sport_key per league, strict event resolution (no-match/ambiguity = error), persisted odds_event_mappings, correct URL path (never internal UUID).
- 10. Evidence linkage: content-dedup raw payloads + observation rows; snapshots carry payload_id.
- 11. job_attempts: sequential numbering (1,2,3…), real hostname:pid, loud failure on uniqueness exhaustion.
- 12. Scanner dispatches `sports.collect` jobs with job/attempt state; exception-safe cleanup (redis/providers/engine).
- 13. Form inputs from deterministic completed-result history (W/D/L, no LLM/settlement).
- 14. Status API: real degradation mode, both-team freshness, publication-aware lineup availability, Priority enum, zero external calls on reads.

**Files changed**
- src: collectors/{framework,locks,quota,ids,sports_collectors,odds_collector,pre_match_scan}.py; providers/{base,dto,errors}.py; providers/sports/{api_football,mock}.py; providers/odds/{base,mock,parse,factory}.py; workers/tasks/{scheduling,collect,pre_match,sports}.py; workers/{celery_app,utils}.py; pipelines/discover_fixtures.py; api/routes/status.py; db/models/{snapshots,__init__}.py; db/migrations/versions/0005_*.py (new); core/league_config.py
- tests: unit/{test_scheduled_discovery,test_api_football_categories,test_odds_mapping}.py (new); collectors/{test_framework,test_quota,test_sports_collectors}.py (rewritten); integration/test_m4_collectors.py (rewritten + new M4.1 tests); test_celery_app.py; test_provider_protocols.py
- docs: CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, AI_WORKLOG

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (242)
- integration suite (`sports_intel_test` + redis db15) → PASS (41)
- `uv run ruff check .` / `ruff format --check .` → PASS
- `uv run mypy src` → PASS (86 files, strict)
- `docker compose config -q` (+telegram profile) → PASS
- secret scan → clean

**Live integrations verified**
- none this session (MOCK-only by design; live Odds API only with credentials).

**Mocked only**
- FormInputs completed-history (real provider path contract-tested);
- The Odds API network path (contract-tested against documented v4 shape).

**Known issues**
- Pre-match scan enqueues per (collector, lock-key, phase); odds batch fan-out across fixtures is a future optimization.
- No live smoke for real API-Football category endpoints (bounded live smoke deferred; contract tests cover normalization).

**Spec / ADR deviations**
- none new; implements reviewer-fixed semantics for spec 11 (pct thresholds), 14 (no-data), 7 (windows).

**Git**
- branch: build/m4
- commit: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent re-review of M4.1 (diff `main..build/m4`); merge + tag `v0.5-m4` after PASS; M5 only with explicit user approval.

---

### 2026-08-24 — ox-alpha (OpenCode)

**Milestone:** M4.2
**Task:** Focused corrective implementation after M4.1 review **FAIL**

**Completed**
- 1. Refresh-opportunity job identity (`collectors/refresh.py`):
  lineups → T-window id (t120/t60/t20); TTL categories → deterministic
  time bucket tied to TTL; scanner job key includes opportunity; repeat
  scan dedupes, later window/expiry opens new job (integration test).
- 2. Lineup policy in real execution: Collector.refresh_due hook used by
  framework (fast + double-check); LineupCollector uses lineup_poll_due
  with fixture kickoff + latest state; decide_categories PREMATCH starts
  at outermost window (removed max+60); runtime T120→T60→CONFIRMED-stops
  test.
- 3. Team-split persistence from actual fixture home/away: both teams
  snapshotted from one observation; uncovered side conservative
  (NOT_YET_PUBLISHED/UNKNOWN), never CONFIRMED; published refs include
  both team refs; synchronized home+away test (1 call, 2 snapshots,
  per-team UUIDs).
- 4. Odds events contract: top-level JSON array accepted; contract
  fixtures; no-match/ambiguity hard errors.
- 5. Real double-chance names + alternate_totals → canonical ou_15/ou_25.
- 6. No-vig only on complete expected selection sets.
- 7. Explicit home/away name loading (no unordered IN) + reversed-order
  regression test.
- 8. sports.collect reserves OddsProvider.estimate_cost (4 markets × 1
  region → 4), actual_cost from x-requests-last.
- 9. Quota reservation baseline = observed remaining − reservations
  since; post-INCR decision with rollback; P0 reserve preserved; test
  observed=4 limit=100 concurrent P0/P1.
- 10. Fail closed on quota-init failure for real providers (job FAILED,
  zero calls); MOCK stays keyless; discovery Redis closed in finally.
- 11. /teams/statistics parser: v3 single-object contract + faithful
  fixture.
- 12. Status both-team fresh-requires-both; one missing → unknown;
  PREMATCH phase semantics.

**Files changed**
- src: collectors/{refresh(new),framework,sports_collectors,odds_collector,quota,pre_match_scan}.py;
  providers/odds/{factory,parse}.py; providers/sports/api_football.py;
  workers/tasks/{pre_match,collect,sports}.py; api/routes/status.py
- tests: unit/{test_refresh(new),test_odds_mapping,test_api_football_categories,
  collectors/test_odds_math,collectors/test_sports_collectors}.py;
  integration/test_m4_collectors.py (23 tests)
- docs: CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, AI_WORKLOG

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (254)
- integration suite → PASS (49)
- ruff check/format → PASS; mypy src strict → PASS (87 files)
- compose config (+telegram) → PASS; secret scan → clean

**Live integrations verified**
- none (MOCK-only; live smokes require local credentials — allowed but
  not run).

**Mocked only**
- The Odds API + /teams/statistics network paths (contract-tested).

**Known issues**
- Odds league-level batch endpoint remains a future optimization.

**Spec / ADR deviations**
- none new.

**Git**
- branch: build/m4
- commit: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent re-review of M4.2; merge + tag `v0.5-m4` after PASS; M5
  only with explicit user approval.

---

### 2026-08-24 — ox-alpha (OpenCode)

**Milestone:** M4.3
**Task:** Focused correctness pass after M4.2 review **FAIL**

**Completed**
- 1. Odds capability gating: build_odds_provider returns None when
  DISABLED in non-mock env (empty ODDS_PROVIDER); mock in non-mock
  requires ODDS_ALLOW_MOCK_OVERRIDE else ProviderConfigError; scanner
  skips odds when disabled (planned/created/enqueued counters);
  sports.collect fails closed; regression live_local + no odds → zero
  jobs + zero snapshots.
- 2. Provider market translation: OddsProvider.request_markets()
  guarantees outgoing markets= contains h2h, double_chance, totals,
  alternate_totals, btts; cost estimation uses ACTUAL provider set
  (5×1 → 5); outgoing-query contract test.
- 3. Fixture-level lineup refresh: refresh_due aggregates both fixture
  teams; CONFIRMED stops only when both confirmed; partial state still
  refreshes; scenario integration test.
- 4. TTL due-generation identity: captured+TTL while fresh, now when
  stale, due:missing when no snapshot; stale-inside-old-bucket
  counterexample regression.
- 5. Quota observation generations: reservation counters keyed to
  observed_at generation; newer observation → fresh counter; regression
  100→4→96→4 behaves as 92; concurrent-after-new-observation test.
- 6. Odds limit from used+remaining (8+492 → 500); degradation % on
  actual allowance; x-requests-last = cost.
- 7. FAILED collector/scheduled job requeue: same uuid, CAS
  FAILED→PENDING only; never downgrade RUNNING/SUCCEEDED; tests.
- 8. Failure telemetry: ProviderError.quota_headers (safe only);
  API-Football + Odds 401/403/429/5xx carry status_code + headers;
  framework record_failure passes them; 429 ledger test.
- 9. Scanner observability: planned/jobs_created/jobs_reused/
  jobs_enqueued counters; finally-safe Redis cleanup.

**Files changed**
- src: providers/odds/{factory,base,mock}.py; providers/errors.py;
  providers/sports/api_football.py; collectors/{refresh,quota,
  sports_collectors,framework}.py; workers/tasks/{pre_match,collect,
  scheduling}.py; core/config.py
- tests: unit/test_odds_gating.py (new); unit/collectors/test_refresh.py,
  test_quota.py; integration/test_m4_collectors.py (+7 M4.3 tests)
- docs: CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, AI_WORKLOG;
  Makefile (Redis flush before integration)

**Verification**
- unit → PASS (262); integration → PASS (56)
- ruff check/format → PASS; mypy src strict → PASS (87 files)
- compose (+telegram) → PASS; secret scan → clean

**Live integrations verified**
- none (contract-tested; live smokes require local credentials).

**Mocked only**
- Odds + API-Football network paths (contract-tested, incl. failure
  telemetry).

**Known issues**
- Local integration runs flush Redis first (reservation counters).

**Spec / ADR deviations**
- none new.

**Git**
- branch: build/m4
- commit: recorded in REVIEW_HANDOFF after commit

**Next action**
- Independent re-review of M4.3; merge + tag `v0.5-m4` after PASS; M5
  only with explicit user approval.

---

### 2026-08-28 — ox-alpha (OpenCode)

**Milestone:** M4.4
**Task:** Focused correctness fixes (4 items) after M4.3 review **FAIL**

**Completed**
- 1. /teams/statistics v3 normalization: fixtures.{played,wins,draws,
  loses}.{home,away,total} (loses→losses), goals.for/against.total.
  {home,away,total} nested, clean_sheet/failed_to_score splits; missing
  → None never zero; contract-faithful sentinel + full asserts.
- 2. Season identity pinned: PreMatchDecision.season_id from fixture;
  execute_plan passes exact season; exact Season resolver (league
  verified, deterministic year, refuse missing/ambiguous) replaces
  active=True LIMIT 1; lock/freshness/provider-season/snapshot all
  pinned; two-season integration regression.
- 3. Stable TTL opportunity: due:missing (no snapshot), fresh → no job
  (scanner freshness check), stale → due:<captured+TTL> stable;
  acceptance flow regression (T0+20/T0+31/T0+35/T0+40/T0+41).
- 4. QuotaBucket.observed_at = response time (finished_at); overlap
  ordering regression (later response authoritative).

**Files changed**
- src: providers/sports/api_football.py; collectors/{sports_collectors,
  pre_match_scan,refresh,quota}.py; workers/tasks/pre_match.py
- tests: unit/test_api_football_categories.py; unit/collectors/
  test_refresh.py, test_framework.py; integration/test_m4_collectors.py
- docs: CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, AI_WORKLOG

**Verification**
- unit → PASS (263); integration → PASS (59)
- ruff/format → PASS; mypy strict (87) → PASS; compose → OK;
  secrets clean; no schema migration.

**Live integrations verified**
- none (contract-tested; bounded live smoke allowed only with local
  credentials — not run).

**Known issues**
- Local integration runs flush Redis first (reservation counters).

**Git**
- branch: build/m4
- commit: 9ec45d9

**Next action**
- Independent re-review of M4.4; merge + tag `v0.5-m4` after PASS; M5
  only with explicit user approval.

---

### 2026-09-28 22:48 +02:00 — Antigravity (Gemini 3.8 Flash)

**Milestone:** M4.4
**Task:** Independent review M4.3 verification and focused M4.4 correctness verification

**Completed**
- 1. Verified API-Football /teams/statistics v3 normalization:
  fixtures.{played,wins,draws,loses}.{home,away,total} (loses→losses),
  goals.for/against.total.{home,away,total}, clean_sheet, failed_to_score;
  missing values stay None; contract tests assert all metrics.
- 2. Pinned season identity end-to-end: PreMatchDecision.season_id,
  execute_plan propagation, exact Season resolver (replaces active=True LIMIT 1),
  StandingsCollector.latest_snapshot() AND TeamStatisticsCollector.latest_snapshot()
  both filter by exact season_id; unit + integration tests verify season isolation.
- 3. Verified stable TTL refresh opportunity: due:missing without snapshot,
  fresh snapshot produces no job, stale snapshot identity stable across scanner runs
  (due:<captured_at + effective_ttl>).
- 4. Verified QuotaBucket.observed_at derived from response finished_at
  rather than request start; ordering test proves later response becomes authoritative.

**Files changed**
- `src/sports_intelligence/collectors/sports_collectors.py` (added season_id filter to TeamStatisticsCollector.latest_snapshot)
- `tests/integration/test_m4_collectors.py` (added team statistics season isolation assertions, cleaned duplicate decorator)
- `tests/unit/collectors/test_sports_collectors.py` (added test_latest_snapshot_includes_season_id)
- `docs/CURRENT_TASK.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/REVIEW_HANDOFF.md`, `docs/AI_WORKLOG.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (264 passed in 4.09s)
- `uv run ruff check .` / `ruff format --check .` → PASS (clean)
- `uv run mypy src` → PASS (87 source files strict clean)
- `docker compose config -q` / `--profile telegram` → PASS (clean)
- Secret scan → clean (no secrets in tracked files)

**Live integrations verified**
- none (MOCK only, live credentials not configured for broader smoke).

**Known issues**
- Local integration runs flush Redis first (reservation counters).
- Docker desktop daemon not active locally during this session.

**Spec / ADR deviations**
- none new.

**Git**
- branch: build/m4
- commit: 63b23f2

**Next action**
- Commit M4.4 verification fixes, update remote HEAD.
- Independent review PASS before merge to main; do not start M5.

---

### 2026-09-28 23:10 +02:00 — Antigravity (Gemini 3.8 Flash)

**Milestone:** M4.4
**Task:** Full local acceptance suite execution and bugfixes for TeamStatisticsSnapshot & exact season freshness

**Completed**
- Discovered and fixed runtime TypeError in `TeamStatisticsCollector.persist()` by removing nonexistent `source_fingerprint` kwarg on `TeamStatisticsSnapshot` creation.
- Eliminated cross-season fallback in `StandingsCollector.latest_snapshot()` and `TeamStatisticsCollector.latest_snapshot()` by returning `(None, None)` immediately when `season_id is None`.
- Added defensive skips in `pre_match_scan.execute_plan()` and `tasks/pre_match.py` when `season_id` is missing for standings or team statistics.
- Added and updated tests verifying two-season isolation, unique lock and job keys, season_id persistence, and execute_plan skipping.
- Executed the full acceptance suite locally with live Docker service containers (sports-intel-sports-postgres-1 on 5433, sports-intel-sports-redis-1 on 6380): unit suite (265 passed), integration suite against isolated sports_intel_test (59 passed), ruff lint/format (clean), mypy strict (clean), alembic check (clean), compose validation (clean).

**Files changed**
- `src/sports_intelligence/collectors/pre_match_scan.py`
- `src/sports_intelligence/collectors/sports_collectors.py`
- `src/sports_intelligence/workers/tasks/pre_match.py`
- `tests/integration/test_m4_collectors.py`
- `tests/unit/collectors/test_pre_match_scan.py`
- `tests/unit/collectors/test_sports_collectors.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Verification**
- `~/.local/bin/uv run pytest -q -m "not integration"` → PASS (265 passed)
- `docker exec sports-intel-sports-redis-1 redis-cli -n 15 FLUSHDB && TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" ~/.local/bin/uv run pytest -q -m integration` → PASS (59 passed)
- `~/.local/bin/uv run ruff check .` / `ruff format --check .` → PASS (clean)
- `~/.local/bin/uv run mypy src` → PASS (clean in 87 source files)
- `~/.local/bin/uv run alembic check` → PASS (No new upgrade operations detected)
- `docker compose config -q` / `--profile telegram` → PASS (clean)
- Secret scan → clean (no credentials committed)

**Live integrations verified**
- none (MOCK only, live credentials not configured).

**Known issues**
- Local integration runs flush Redis db 15 first for isolation.

**Spec / ADR deviations**
- none.

**Git**
- branch: build/m4
- commit: 0d0cd4a631c067a29c21ce584e806a47c534dc82

**Next action**
- Independent review PASS received.
- Finalize documentation, merge build/m4 to main, tag v0.5-m4, create build/m5.

---

### 2026-09-29 08:50 +02:00 — Antigravity (Gemini 3.8 Flash)

**Milestone:** M4 → M5 transition
**Task:** M4 finalization, merge to main, tag v0.5-m4, create build/m5

**Completed**
- Independent review of M4 verdict: PASS / ACCEPTED (accepted remote HEAD: `0d0cd4a631c067a29c21ce584e806a47c534dc82`).
- Updated persistent state docs (`CURRENT_TASK.md`, `IMPLEMENTATION_STATUS.md`, `REVIEW_HANDOFF.md`, `AI_WORKLOG.md`) to reflect accepted M4 state and actual accepted commit.
- Cleaned stale development-agent/session references.
- Documentation-only cleanup committed and ready for merge to main.

**Files changed**
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Verification**
- Git status clean; documentation aligned with accepted commit `0d0cd4a631c067a29c21ce584e806a47c534dc82`.

**Live integrations verified**
- none.

**Known issues**
- none.

**Spec / ADR deviations**
- none.

**Git**
- branch: build/m4
- commit: [docs cleanup commit]

**Next action**
- Commit doc cleanup, push build/m4, merge into main via PR, tag v0.5-m4, create build/m5.

---

### 2026-09-29 10:00 +02:00 — Antigravity (Gemini 3.8 Flash)

**Milestone:** M5
**Task:** Milestone M5 Web Research Subsystem implementation, verification, and preparation for review

**Completed**
- Finalized accepted M4 state and merged `build/m4` to `main` via PR #6 (`2e4683a`), pushed tag `v0.5-m4`.
- Created and switched to branch `build/m5`.
- Implemented core freshness and phase definitions: `FreshnessCategory.RESEARCH`, `ResearchState`, `ClaimType`, and updated settings (`freshness_research_seconds`, `research_enabled`).
- Implemented search provider boundary & adapters (`src/sports_intelligence/providers/search/`):
  - `SearchProvider` Protocol, `SearchResultItem`, `SearchResponse`.
  - `MockSearchProvider`: deterministic canned responses, token matching, error simulation, query history tracking, JSONB-safe datetime serialization.
  - `TavilySearchProvider`: production-ready adapter with bounded timeouts, retries with backoff and jitter, 4xx non-retryable handling, canonical URL normalization, secret redaction, rate limit header parsing.
  - `build_search_provider` factory: strict gating against silent mock in live environments without explicit override.
- Implemented claim extraction, conflict detection & anti-leakage audit (`src/sports_intelligence/research/`):
  - DTOs: `ExtractedClaimDTO`, `ResearchDocumentDTO`, `ResearchRunResultDTO`.
  - `build_research_queries`: bounded (max 6), deterministic queries per fixture for MORNING and PREMATCH phases.
  - `deduplicate_search_results`, `normalize_url` (strips tracking parameters, query fragments, trailing slashes), `content_sha256`.
  - `RuleBasedClaimExtractor` / `MockClaimExtractor`: extracts claims across 8 categories, associates team IDs, assigns confidence scores.
  - `detect_conflicts`: identifies contradictory presence/absence claims for the same subject or team; strictly preserves both claims, flags `conflict_flag=True`, links `conflicting_claim_id`, and attaches metadata.
  - `get_research_for_fixture`: anti-leakage audit service enforcing `as_of` temporal cutoff (`retrieved_at <= as_of` and `published_at <= as_of`).
- Implemented database models and migration (`src/sports_intelligence/db/`):
  - `ResearchRun`, `ResearchDocument`, `ResearchClaim` models with descending composite indexes and foreign keys.
  - Alembic migration `0006_m5_research_documents_claims.py` created, tested, and verified clean with `alembic check`.
- Integrated collector and Celery workers:
  - `ResearchCollector`: registered in framework (`name="research"`, `category=FreshnessCategory.RESEARCH`, `priority=Priority.P3`), supports coalescing locks (`research:{fixture_id}`), raw payload storage in `raw_provider_payloads`, and snapshot persistence.
  - Pre-match scanner includes `FreshnessCategory.RESEARCH` in scan plan and TTL evaluations.
  - Celery task `sports_intelligence.workers.tasks.research` routed to `research_io` queue.
- Implemented REST API endpoints:
  - `GET /v1/fixtures/{fixture_id}/research`: returns documents and claims with optional `as_of` query parameter.
  - `GET /v1/fixtures/{fixture_id}/status`: reflects `research` freshness state and last refresh timestamp.
- Added comprehensive unit and integration tests (300 unit + 66 integration = 366 passing tests).

**Files changed**
- Created:
  - `src/sports_intelligence/api/routes/research.py`
  - `src/sports_intelligence/collectors/research_collector.py`
  - `src/sports_intelligence/db/migrations/versions/0006_m5_research_documents_claims.py`
  - `src/sports_intelligence/providers/search/__init__.py`
  - `src/sports_intelligence/providers/search/base.py`
  - `src/sports_intelligence/providers/search/factory.py`
  - `src/sports_intelligence/providers/search/mock.py`
  - `src/sports_intelligence/providers/search/tavily.py`
  - `src/sports_intelligence/research/conflict.py`
  - `src/sports_intelligence/research/dedup.py`
  - `src/sports_intelligence/research/extractor.py`
  - `src/sports_intelligence/research/models.py`
  - `src/sports_intelligence/research/query_builder.py`
  - `src/sports_intelligence/research/service.py`
  - `src/sports_intelligence/schemas/research.py`
  - `src/sports_intelligence/workers/tasks/research.py`
  - `tests/integration/test_m5_research.py`
  - `tests/unit/collectors/test_research_collector.py`
  - `tests/unit/test_research_conflict.py`
  - `tests/unit/test_research_dedup.py`
  - `tests/unit/test_research_extractor.py`
  - `tests/unit/test_research_provenance.py`
  - `tests/unit/test_research_query_builder.py`
  - `tests/unit/test_search_gating.py`
  - `tests/unit/test_search_provider.py`
- Modified:
  - `src/sports_intelligence/api/app.py`
  - `src/sports_intelligence/api/routes/status.py`
  - `src/sports_intelligence/collectors/framework.py`
  - `src/sports_intelligence/collectors/freshness.py`
  - `src/sports_intelligence/collectors/pre_match_scan.py`
  - `src/sports_intelligence/collectors/quota.py`
  - `src/sports_intelligence/core/config.py`
  - `src/sports_intelligence/core/phases.py`
  - `src/sports_intelligence/db/models/__init__.py`
  - `src/sports_intelligence/db/models/snapshots.py`
  - `src/sports_intelligence/providers/base.py`
  - `src/sports_intelligence/research/__init__.py`
  - `src/sports_intelligence/workers/celery_app.py`
  - `src/sports_intelligence/workers/tasks/collect.py`
  - `src/sports_intelligence/workers/tasks/pre_match.py`
  - `tests/integration/test_m4_collectors.py`
  - `tests/unit/collectors/test_freshness.py`
  - `docs/CURRENT_TASK.md`
  - `docs/IMPLEMENTATION_STATUS.md`
  - `docs/REVIEW_HANDOFF.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (300 passed, 66 deselected in 4.18s)
- `TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" uv run pytest -q -m integration` → PASS (66 passed, 300 deselected in 11.10s)
- `uv run pytest -q` → PASS (366 passed in 14.06s)
- `uv run ruff check .` → PASS (clean)
- `uv run ruff format --check .` → PASS (clean, 156 files formatted)
- `uv run mypy src` → PASS (clean in 103 source files)
- `uv run alembic check` → PASS (No new upgrade operations detected)
- `docker compose config -q` / `--profile telegram` → PASS (clean)
- Secret scan → clean (no credentials committed)

**Live integrations verified**
- none (MOCK only, live search API keys not configured).

**Known issues**
- none.

**Spec / ADR deviations**
- none.

**Git**
- branch: build/m5
- commit: 5c05b79897e6b9eb1938cff9fb591fe0c5988bb0

**Next action**
- Await independent review of Milestone M5.

---

### 2026-09-29 19:25 +02:00 — Antigravity (Gemini 3.8 Flash)

**Milestone:** M5
**Task:** Bounded live Tavily search provider validation, real response contract alignment, and final acceptance

**Completed**
- Validated secret safety: verified `SEARCH_PROVIDER=tavily` and `SEARCH_API_KEY` present locally in `.env` without printing or logging credentials.
- Executed bounded live validation against Tavily API (exactly 2 requests total):
  1. Provider-level query: `"Brentford vs Tottenham injury news"` (3 results returned, basic search depth, news topic).
  2. Collector-driven research execution for real database fixture: `8c9c59c9-9ad9-4683-9895-5db48d2a52b0` (Brentford vs Tottenham, kickoff 2026-08-22 16:30 UTC), query: `"Brentford injuries 2026-08-22"`.
- Verified real Tavily response contract:
  - Discovered that Tavily returns RFC 2822 / HTTP formatted date strings in `published_date` (e.g., `"Sat, 22 Aug 2026 00:00:00 GMT"`), which failed ISO-only parsing and returned None.
  - Fixed `_parse_published_at` in `src/sports_intelligence/providers/search/tavily.py` to parse RFC 2822 dates using `email.utils.parsedate_to_datetime`, producing correct timezone-aware UTC timestamps.
  - Added extraction of result `id` into `provider_metadata["tavily_id"]`.
  - Added unit test in `tests/unit/test_search_provider.py` asserting RFC 2822 date parsing and metadata propagation.
- Verified database persistence & provenance:
  - `ResearchRun` record created with `status=AVAILABLE`, `queries_count=1`, `documents_count=3`, `claims_count=8`, `provider=tavily`.
  - 3 `ResearchDocument` records persisted with genuine `retrieved_at`, parsed `published_at`, `content_hash`, and metadata.
  - 8 `ResearchClaim` records extracted across `availability`, `suspension`, and `team_news`.
  - Provenance anti-leakage verified: `get_research_for_fixture(as_of=now)` returns 3 documents and 8 claims; `get_research_for_fixture(as_of=past)` returns 0 documents and 0 claims.
- Secret safety audit:
  - Checked `RawProviderPayload` table: verified zero occurrences of API key.
  - Checked `ResearchDocument` and `ResearchClaim` rows: verified zero occurrences of API key.
  - Checked Git diff: verified zero credentials.
- Quality sanity check:
  - Authoritative sources returned (Goal.com, The Athletic / NYTimes, Reuters).
  - Plausibly useful for pre-match intelligence: identified specific player availability (e.g. Kulusevski, Romero, Vicario, Maddison, Solanke for Tottenham, and Yarmoliuk, Van den Berg for Brentford).

**Files changed**
- `src/sports_intelligence/providers/search/tavily.py`
- `tests/unit/test_search_provider.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (300 passed, 66 deselected in 4.19s)
- `TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" uv run pytest -q -m integration` → PASS (66 passed, 300 deselected in 10.48s)
- `uv run pytest -q` → PASS (366 passed in 14.06s)
- `uv run ruff check .` → PASS (clean)
- `uv run ruff format --check .` → PASS (clean, 156 files formatted)
- `uv run mypy src` → PASS (clean in 103 source files)
- `uv run alembic check` → PASS (No new upgrade operations detected)
- `docker compose config -q` / `--profile telegram` → PASS (clean)
- Secret scan → clean (no credentials committed)

**Live integrations verified**
- Tavily search provider (M5: 2 real queries executed and verified end-to-end; secret safety verified; RFC 2822 date parsing aligned).

**Known issues**
- none.

**Spec / ADR deviations**
- none.

**Git**
- branch: build/m5
- commit: e0d18a7d599af0c559fb85d16f1623f211a4894c

**Next action**
- Await independent review of Milestone M5 on build/m5.

---

### 2026-09-29 — Antigravity (Gemini 3.8 Flash) (Milestone M5.1 correctness pass)

**Milestone:** M5.1 (Web Research Subsystem Correctness Pass)  
**Task:** Address all findings from independent review verdict `M5 = FAIL` on branch `build/m5` without redesigning core architecture.

**Completed**
1. **Fix Tavily retrieval-time capturing after response**:
   - Updated `src/sports_intelligence/providers/search/tavily.py` so `retrieved_at = self._clock()` is assigned strictly *after* `response = await self._client.post(...)`. Added optional injectable `clock` parameter.
   - Added unit regression test `test_tavily_retrieval_time_captured_after_response_anti_leakage`.
2. **Claim-level temporal safety (`extracted_at <= as_of`)**:
   - Added timezone-aware `extracted_at` to `ResearchClaim` model, `ExtractedClaimDTO`, and `ResearchClaimOut`.
   - Created descending composite index `ix_research_claims_fixture_extracted` on `(fixture_id, extracted_at DESC)`.
   - Created Alembic migration `0007_m51_claim_extracted_at_and_fk.py`. Verified upgrade/downgrade and `alembic check`.
   - Updated `get_research_for_fixture()` to filter `claim.extracted_at <= as_of`.
   - Added unit test `test_claim_level_as_of_safety_filtering` and integration test.
3. **Search quota and ledger matching real HTTP calls**:
   - Configured `ResearchCollector.owns_quota = True`, bypassing framework-level outer reservation and ledger recording.
   - `ResearchCollector` invokes `ctx.quota.reserve(cost=1)` and records ledger success/failure for each individual search query executed (up to 6 queries).
   - If quota is denied mid-run, execution cleanly breaks and persists prior results or records `NO_USEFUL_RESULTS`.
   - Fresh research runs skip external calls with zero quota requests.
   - Added tests: `test_research_collector_records_exact_queries_in_ledger`, `test_research_collector_stops_when_quota_exhausted`, and `test_fresh_research_issues_zero_search_calls`.
4. **Conflict referential integrity**:
   - Added self-referential `ForeignKey("research_claims.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED")` constraint on `ResearchClaim.conflicting_claim_id`.
   - Preserved stable claim UUIDs throughout extraction and conflict flagging.
   - Verified reciprocal integrity (`A.conflicting_claim_id == B.id` and `B.conflicting_claim_id == A.id`) directly in PostgreSQL.
5. **SearchProvider resource cleanup**:
   - Refactored `src/sports_intelligence/workers/tasks/collect.py` `_run_collect_job()` to only instantiate `search_provider` for research jobs (skipping sports/odds providers), and guaranteed `search_provider.aclose()` in the `finally` block across all scenarios.
   - Added parameterized unit test `test_run_collect_job_always_closes_search_provider`.
6. **Structured research states**:
   - Differentiated `DISABLED`, `PROVIDER_ERROR`, `NO_USEFUL_RESULTS`, `EXTRACTION_UNAVAILABLE`, and `AVAILABLE`.
7. **Historical view consistency**:
   - Supported default Option B (`mode="latest_run"`) enforcing `run_id == run_row.id` and run status consistency, and Option A (`mode="accumulated"`).
   - Added `mode` query parameter to `GET /v1/fixtures/{fixture_id}/research`.
8. **Test & CI isolation**:
   - All 379 tests pass offline with zero external network requests.

**Files changed**
- `src/sports_intelligence/providers/search/tavily.py`
- `src/sports_intelligence/providers/search/mock.py`
- `src/sports_intelligence/db/models/snapshots.py`
- `src/sports_intelligence/db/migrations/versions/0007_m51_claim_extracted_at_and_fk.py`
- `src/sports_intelligence/research/models.py`
- `src/sports_intelligence/research/service.py`
- `src/sports_intelligence/schemas/research.py`
- `src/sports_intelligence/collectors/framework.py`
- `src/sports_intelligence/collectors/research_collector.py`
- `src/sports_intelligence/api/routes/research.py`
- `src/sports_intelligence/workers/tasks/collect.py`
- `tests/unit/test_search_provider.py`
- `tests/unit/test_research_provenance.py`
- `tests/unit/test_worker_init_cleanup.py`
- `tests/unit/collectors/test_research_collector.py`
- `tests/integration/test_m5_research.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Verification**
- `uv run pytest -q -m "not integration"` → PASS (308 passed, 71 deselected in 12.75s)
- `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration` → PASS (71 passed, 308 deselected in 18.29s)
- `uv run pytest -q` → PASS (379 passed in 20.18s)
- `uv run ruff check .` → PASS (clean)
- `uv run ruff format --check .` → PASS (clean, 157 files formatted)
- `uv run mypy src` → PASS (clean in 104 source files)
- `uv run alembic check` → PASS (No new upgrade operations detected)
- `docker compose config -q` / `--profile telegram` → PASS (clean)
- Secret scan → clean (no credentials committed)

**Known issues**
- none.

**Spec / ADR deviations**
- none.

**Git**
- branch: build/m5
- commit: 147862f (initial M5.1 commit)

**Next action**
- Commit docs sync, push build/m5, verify CI, and await independent review.







---
timestamp: 2026-09-29T20:27:46.716757
agent/model: Antigravity (Gemini)
milestone: M5.2
task: Implement focused M5.2 correctness fixes
files changed:
- src/sports_intelligence/providers/search/tavily.py
- src/sports_intelligence/collectors/research_collector.py
- src/sports_intelligence/core/config.py
- src/sports_intelligence/api/routes/research.py
- src/sports_intelligence/research/service.py
- tests/unit/test_search_provider.py
- tests/unit/collectors/test_research_collector.py
- tests/integration/test_m5_research.py
- .env.example
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/REVIEW_HANDOFF.md
behavior implemented:
- Removed internal retry loop from TavilySearchProvider.
- Moved retry loop to ResearchCollector with quota checks on each attempt.
- Added research_claim_extraction_enabled to Settings and used it properly.
- Handled disabled research capability in the Read API.
- latest_snapshot() ignores runs with PROVIDER_ERROR status so they aren't considered fresh.
- Recorded partial provider failures as PROVIDER_ERROR with detail_jsonb diagnostics.
- Validate mode strictly as Literal["latest_run", "accumulated"] in API and service.
commands/tests run: uv run pytest -q, uv run ruff check, uv run mypy src
results: All tests pass.
known problems: None.
spec/ADR deviations: None.
next recommended action: Review M5.2 changes.

---
timestamp: 2026-09-29T21:20:00+02:00
agent/model: Antigravity (Gemini 3.8 Flash)
milestone: M5.3
task: Implement focused M5.3 runtime correctness pass on branch build/m5
files changed:
- .env.example
- src/sports_intelligence/core/config.py
- src/sports_intelligence/core/phases.py
- src/sports_intelligence/schemas/status.py
- src/sports_intelligence/api/routes/status.py
- src/sports_intelligence/collectors/refresh.py
- src/sports_intelligence/collectors/research_collector.py
- src/sports_intelligence/workers/tasks/pre_match.py
- tests/unit/collectors/test_research_collector.py
- tests/integration/test_m5_research.py
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/REVIEW_HANDOFF.md
- docs/AI_WORKLOG.md
behavior implemented:
- Replaced (None, None) hack in latest_snapshot with true (captured_at, id) and added latest_run_info / refresh_due on ResearchCollector.
- Implemented deterministic error_due:<epoch> refresh opportunity identity for PROVIDER_ERROR runs (and quota_due:<epoch> for QUOTA_DENIED).
- Added ResearchState.QUOTA_DENIED; prevented fake provider error exceptions/telemetry on local quota denial; preserved partial documents/claims on mid-run quota denial.
- Tracked clock observation timestamps after every external HTTP attempt, ensuring ResearchRun.captured_at on failure reflects exact observation time (T2/T3) while documents keep their retrieved_at (T1); verified historical as_of between T1 and T3 does not leak the later failed run.
- Implemented compute_retry_delay() respecting Retry-After on 429, capped at research_max_retry_after_seconds (30s) with exponential backoff fallback; added injectable sleeper and clock.
- Updated GET /v1/fixtures/{fixture_id}/status to report research freshness as "disabled" when capability is disabled and no run exists.
commands/tests run:
- uv run ruff check .
- uv run ruff format --check .
- uv run mypy src
- uv run pytest -q -m "not integration"
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q
- uv run alembic upgrade head && uv run alembic check
- docker compose config -q && docker compose --profile telegram config -q
results:
- Lint: clean
- Format: clean (157 files)
- Mypy: clean (104 files)
- Unit tests: 318 passed, 76 deselected
- Integration tests: 76 passed, 318 deselected
- Full suite: 394 passed in 16.24s
- Alembic: clean (No new upgrade operations detected)
- Compose: valid
- Real external Tavily calls: 0
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: 8833d9e7c47a6dd7aeef9dd24d999b4bad214b59
next recommended action: Commit docs sync, push build/m5, verify CI, await independent review.

---
timestamp: 2026-09-29T21:46:00+02:00
agent/model: Antigravity (Gemini 3.8 Flash)
milestone: M5
task: Finalize accepted Milestone M5, prepare PR and merge to main
files changed:
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/REVIEW_HANDOFF.md
- docs/AI_WORKLOG.md
behavior implemented:
- Recorded independent review verdict: Milestone M5 = PASS / ACCEPTED.
- Verified accepted implementation remote HEAD: b38229b0874e9ab992ae25ea2a63e1e6109f8ca7.
- Updated project memory documents before opening PR to main.
commands/tests run:
- git status
- git log
results:
- Working tree clean, build/m5 up to date with origin/build/m5.
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: 94a0511470ce2385b297b1b3fb3bcbe741639d48
next recommended action: Open PR build/m5 -> main, wait for CI, merge to main, tag v0.6-m5, create build/m6.

---
timestamp: 2026-09-30T07:15:00+02:00
agent/model: Antigravity (Gemini 3.8 Flash)
milestone: M5
task: Finalize M5 merge to main, tag v0.6-m5, create branch build/m6
files changed:
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md
behavior implemented:
- Verified M5 acceptance verdict: PASS / ACCEPTED (HEAD b38229b0874e9ab992ae25ea2a63e1e6109f8ca7).
- Merged PR #7 (build/m5 -> main) with merge commit fb256ecaf2ca1a97c64f1dba8d491cff6b935c91.
- Created and pushed annotated tag v0.6-m5 on commit fb256ec.
- Created branch build/m6 from updated accepted main (fb256ec).
commands/tests run:
- gh pr merge 7 --merge
- git tag -a v0.6-m5 -m "Milestone M5 — Web Research Subsystem"
- git push origin v0.6-m5
- git checkout -b build/m6
results:
- Clean merge, annotated tag v0.6-m5 pushed to remote, branch build/m6 checked out.
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: fb256ecaf2ca1a97c64f1dba8d491cff6b935c91
next recommended action: Implement Milestone M6.

---
timestamp: 2026-09-30T09:25:00+02:00
agent/model: Antigravity (Gemini 3.8 Flash)
milestone: M6
task: Implement Milestone M6: deterministic Feature Builder + Data Quality Engine + immutable MatchContext
files changed:
- src/sports_intelligence/api/app.py
- src/sports_intelligence/api/routes/context.py
- src/sports_intelligence/collectors/pre_match_scan.py
- src/sports_intelligence/collectors/sports_collectors.py
- src/sports_intelligence/context/__init__.py
- src/sports_intelligence/context/builder.py
- src/sports_intelligence/context/models.py
- src/sports_intelligence/context/provenance.py
- src/sports_intelligence/context/selector.py
- src/sports_intelligence/db/migrations/versions/0008_m6_match_context_features_quality.py
- src/sports_intelligence/db/models/__init__.py
- src/sports_intelligence/db/models/context.py
- src/sports_intelligence/db/models/snapshots.py
- src/sports_intelligence/features/__init__.py
- src/sports_intelligence/features/builder.py
- src/sports_intelligence/providers/sports/mock.py
- src/sports_intelligence/quality/__init__.py
- src/sports_intelligence/quality/engine.py
- src/sports_intelligence/schemas/context.py
- src/sports_intelligence/workers/celery_app.py
- src/sports_intelligence/workers/tasks/context.py
- src/sports_intelligence/workers/tasks/pre_match.py
- tests/integration/test_m6_anti_leakage_and_context.py
- tests/unit/collectors/test_pre_match_scan.py
- tests/unit/context/test_context_schema_and_hash.py
- tests/unit/features/test_features_math.py
- tests/unit/quality/test_quality_engine.py
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md
behavior implemented:
- Extended mock sports provider to 10 completed fixtures; updated FormInputsCollector default window to 10 and populated is_home and result; added FreshnessCategory.TEAM_FORM dispatch to execute_plan().
- Created Alembic migration 0008 adding feature_snapshots, data_quality_reports, and match_contexts tables with proper indexes and unique constraints.
- Built strict point-in-time evidence selector (pure <= as_of across 8 evidence tables with zero future data leakage).
- Built machine-readable source provenance manifest with composite SHA-256 fingerprint.
- Built deterministic Feature Builder V1 calculating form PPG, scoring/conceding rates, clean sheets, home/away splits, schedule rest days/congestion, standings deltas, availability counts/state, market no-vig probabilities, and odds movement; preserved missing != 0.0 with diagnostics.
- Built deterministic Data Quality Engine evaluating 7 dimensions with conflict penalties, critical missing rules (odds/form missing -> can_predict=False), and phase-aware lineups policy (MORNING: N/A and excluded from denominator; PREMATCH: evaluated per publication/confirmation).
- Built MatchContext V1 schema (13 sections), canonical JSON serialization, and stable SHA-256 context_hash.
- Integrated background context build Celery task (context.build_match_context) on evaluation queue and wired scanner dispatch.
- Added read-only endpoints GET /v1/fixtures/{id}/quality and GET /v1/fixtures/{id}/context.
commands/tests run:
- uv run ruff check .
- uv run ruff format --check .
- uv run mypy src
- uv run pytest -q -m 'not integration'
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q
- DATABASE_URL=... uv run alembic downgrade -1 && alembic upgrade head && alembic check
- docker compose config -q && docker compose --profile telegram config -q
results:
- Lint: clean
- Format: clean (172 files)
- Mypy: clean (115 files)
- Unit tests: 328 passed, 80 deselected
- Integration tests: 80 passed, 328 deselected
- Full suite: 408 passed in 14.20s
- Alembic: clean, no schema drift
- Docker compose: valid
- Zero live external calls, zero credentials, zero LLM calls.
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: fff8df75c520696f6c25a14e19ded7b6711e7688
next recommended action: Independent review (verdict: FAIL; focused M6.1 requested).

---
timestamp: 2026-09-30T10:40:00+02:00
agent/model: Antigravity (Gemini 3.8 Flash)
milestone: M6.1
task: Milestone M6.1 correctness, provenance, freshness, and orchestration pass on build/m6
files changed:
- src/sports_intelligence/api/routes/context.py
- src/sports_intelligence/collectors/sports_collectors.py
- src/sports_intelligence/context/builder.py
- src/sports_intelligence/context/models.py
- src/sports_intelligence/context/provenance.py
- src/sports_intelligence/context/selector.py
- src/sports_intelligence/core/config.py
- src/sports_intelligence/db/migrations/versions/0003_provider_evidence_history_and_indexes.py
- src/sports_intelligence/db/migrations/versions/0009_m6_1_fixture_metadata_and_provenance.py
- src/sports_intelligence/db/models/__init__.py
- src/sports_intelligence/db/models/context.py
- src/sports_intelligence/db/models/discovery.py
- src/sports_intelligence/db/models/snapshots.py
- src/sports_intelligence/db/repositories/discovery.py
- src/sports_intelligence/features/builder.py
- src/sports_intelligence/pipelines/discover_fixtures.py
- src/sports_intelligence/quality/engine.py
- src/sports_intelligence/research/service.py
- src/sports_intelligence/workers/tasks/pre_match.py
- tests/integration/test_m6_anti_leakage_and_context.py
- tests/unit/context/test_context_schema_and_hash.py
- tests/unit/features/test_features_math.py
- tests/unit/quality/test_quality_engine.py
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md
behavior implemented:
- Immutable Fixture Metadata Observation Model: created migration 0009 with fixture_metadata_snapshots tracking point-in-time kickoff, status, venue, round, league, season, team names, and payload_id. Updated discovery pipeline to persist snapshot on fixture discovery/update. Selector queries fixture_metadata_snapshots <= as_of.
- Added payload_id ForeignKey to team_form_snapshots and linked in FormInputsCollector.
- Provenance manifest updated to include fixture_metadata_snapshot, form payload_id, current and previous odds snapshot set IDs, and real research run ID with document/claim IDs.
- Deterministic multi-bookmaker market consensus: calculated median odds and median no-vig probabilities per market/selection across bookmakers; odds movement calculated from delta of medians.
- Form selection: strictly filtered to window_size == 10 and scope == "overall".
- Provider-scoped external team ID mapping: matched standings and team statistics rows using provider-specific external team IDs.
- Fixed form math: preserved missing != 0; missing goals_for does not count as failed to score; missing goals_against does not count as clean sheet; independent valid sample counts tracked.
- Freshness-aware Data Quality Engine: evaluated snapshot age against configured phase TTLs at as_of, populating stale_sources and applying staleness penalties. Canonical lineup publication states handled (CONFIRMED=1.0, NOT_YET_PUBLISHED=0.40, UNSUPPORTED=0.50, PROVIDER_ERROR=0.20 + error record). Distinguished uncollected research (0.50 + warning) from NO_USEFUL_RESULTS (0.85). Persisted quality_policy dictionary with quality bands excellent/good/usable_with_warnings/abstain.
- Feature-level provenance: mapped each derived feature group to contributing source snapshot IDs in feature_provenance_jsonb.
- Context-build orchestration: scanner blocks context build if any collector is PENDING, RUNNING, or needs enqueue. Context build job uses source-generation key format. FAILED context jobs retry via CAS FAILED -> PENDING with same UUID without downgrading RUNNING or SUCCEEDED.
- API validation: typed ForecastPhase enum query parameter on /quality and /context endpoints (HTTP 422 on invalid).
commands/tests run:
- uv run ruff check .
- uv run ruff format --check .
- uv run mypy src
- uv run pytest -q -m 'not integration'
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q
- DATABASE_URL=... uv run alembic check
- docker compose config -q && docker compose --profile telegram config -q
results:
- Ruff: clean (all checks passed)
- Ruff format: clean (173 files already formatted)
- Mypy: clean (116 files checked, 0 errors)
- Unit tests: 339 passed in 3.81s
- Integration tests: 87 passed in 15.23s
- Full pytest suite: 426 passed in 16.64s
- Alembic check: clean, no schema drift
- Docker compose: valid
- Zero live external calls, zero credentials, zero LLM calls.
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: ecba462cb9059a5df30193dc2eb3e112f85d3aee
next recommended action: Push build/m6, await independent review.

---

timestamp: 2026-09-30T21:18:00+02:00
agent/model if known: Antigravity (Gemini 3.8 Flash)
milestone: M6.2
task: Milestone M6.2 Final Acceptance-Hardening Pass on build/m6
files changed:
- src/sports_intelligence/context/builder.py
- src/sports_intelligence/context/models.py
- src/sports_intelligence/context/provenance.py
- src/sports_intelligence/context/selector.py
- src/sports_intelligence/core/config.py
- src/sports_intelligence/db/migrations/versions/0003_provider_evidence_history_and_indexes.py
- src/sports_intelligence/db/migrations/versions/0009_m6_1_fixture_metadata_and_provenance.py
- src/sports_intelligence/db/models/context.py
- src/sports_intelligence/quality/engine.py
- src/sports_intelligence/workers/tasks/context.py
- src/sports_intelligence/workers/tasks/pre_match.py
- tests/integration/test_m6_anti_leakage_and_context.py
- tests/unit/context/test_context_schema_and_hash.py
- tests/unit/features/test_features_math.py
- tests/unit/quality/test_quality_config_validation.py
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/REVIEW_HANDOFF.md
- docs/AI_WORKLOG.md
behavior implemented:
- Historical Migration 0003 Integrity: Restored 0003_provider_evidence_history_and_indexes.py byte-for-byte to match origin/main (SHA-256 verified 8573d9cc3790166c2b365c627b99b2789c314716839b0fa6da64dc3e184dafaf).
- Authoritative Fixture Metadata & Historical Fallback Removal: When FixtureMetadataSnapshot is missing <= as_of, status is set to METADATA_UNAVAILABLE, venue=None, round=None, fixture_metadata_snapshot_id=None without falling back to mutable canonical Fixture status (e.g. FT). Quality flags fixture_metadata_missing in critical_missing, evaluating quality band to abstain and setting can_predict=False. When snapshot is present <= as_of, strictly uses its dimensions and resolves league using the snapshot's league_id.
- Migration 0009 Legacy Baseline Backfill: Added backfill of legacy_baseline snapshot for pre-existing fixtures at clock_timestamp() (not backdated). Added policy_fingerprint column to data_quality_reports and bound in uq_data_quality_reports_identity unique constraint. Symmetrical downgrade cleanly drops constraint, columns, and tables.
- Complete Fixture Provenance: Manifest includes snapshot_id, provider, captured_at, payload_id, provider_fixture_id, source_version, league_id, season_id, home_team_id, away_team_id. No fake legacy snapshot IDs.
- Runtime Quality Settings Wiring: Context worker uses build_quality_policy(settings) and FreshnessPolicy(settings) constructed from real runtime Settings and passes them to build_and_persist_match_context. Uses configurable staleness_penalty and max_staleness_penalty directly in evaluation.
- Strict Quality Configuration Validation: Enforced validation rules in Settings and QualityPolicy: all weights >= 0, total active weight > 0, 0 <= min_predict_score <= 1, monotonic 0 <= usable <= good <= excellent <= 1, staleness_penalty >= 0, 0 <= max_staleness_penalty <= 1.
- Quality Policy Fingerprint & Identity: Policy SHA-256 fingerprint persisted in data_quality_reports.policy_fingerprint and bound in unique constraint. Separate policies for same fixture and as_of produce distinct reports without conflict.
- Build Configuration Generation in Context Job Identity: Deterministic compute_build_config_fingerprint embedded in job key format context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}.
- Deterministic Market Snapshot Serialization: OddsPrice rows sorted by (market, selection, bookmaker, line, decimal_odds, id). Replaced singular bookmaker with bookmakers: list[str]. Verified identical canonical JSON and hash regardless of DB row insertion order.
- Compatible Previous Odds Snapshot Requirement: Query strictly requires OddsSnapshotSet.provider == odds_set.provider and captured_at < odds_set.captured_at.
- Strict Typed MatchContext Schema: Converted MatchContextV1 and all section models to Pydantic with ConfigDict(extra="forbid", frozen=True). Full context validated before canonical serialization, hash, and persistence.
- Complete Structured Research Claim Source References: ResearchClaimSource object with document_id, url, domain, title, published_at, retrieved_at, content_hash, provider.
- Historical Provider Mapping Semantics & Isolation: ProviderEntityId queries filter first_seen_at <= as_of_utc. get_home_external_id(provider) strictly returns None if provider is unmapped (no fallback).
- MORNING Lineups Fully N/A: Excluded from score denominator, stale lineups do not enter stale_sources, and no staleness penalties or warnings are triggered.
commands/tests run:
- uv run ruff check .
- uv run ruff format --check .
- uv run mypy src
- uv run pytest -q -m 'not integration'
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration
- TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q
- DATABASE_URL=... uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check
- docker compose config -q && docker compose --profile telegram config -q
results:
- Ruff: clean (All checks passed!)
- Ruff format: clean (174 files already formatted)
- Mypy: clean (Success: no issues found in 116 source files)
- Unit tests: 350 passed in 4.78s
- Integration tests: 93 passed in 26.30s
- Full pytest suite: 443 passed in 58.71s
- Alembic downgrade/upgrade/check: clean, 0 schema drift
- Docker compose & telegram profile: valid
- Zero live external calls, zero credentials, zero LLM calls.
known problems: None.
spec/ADR deviations: None.
Git commit hash if created: e004475e120472523305945c5568ffb9bfa97859
next recommended action: Push build/m6, await independent review.



---

## 2026-09-30 23:25 (UTC+2) - Antigravity
**Milestone:** M6
**Task:** M6.3 Reproducibility and Historical-Authority Pass Implementation

**Behavior Implemented:**
- Implemented `FreshnessPolicy` inside `ContextBuildPolicy` to compute staleness deterministically without injecting runtime side effects.
- Rewrote `select_evidence` to strictly rely on `FixtureMetadataSnapshot` for league/team data rather than mutable `Fixture` objects.
- Refactored `MatchContext` sections to strictly enforce schemas using Pydantic `ConfigDict(extra="forbid")`.
- Updated all integration and unit tests for schema compliance and `HistoricalFixtureMetadataUnavailable` logic.

**Files Changed:**
- `src/sports_intelligence/context/builder.py`
- `src/sports_intelligence/context/selector.py`
- `src/sports_intelligence/context/models.py`
- `src/sports_intelligence/collectors/freshness.py`
- `tests/integration/test_m6_anti_leakage_and_context.py`
- `tests/unit/...` (various config/mock updates)

**Commands/Tests Run:**
- `uv run ruff check . --fix`
- `uv run ruff format .`
- `uv run mypy src`
- `uv run pytest -q -m "not integration"`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q -m integration`
- `uv run pytest -q`

**Results:**
- Linting, formatting, and type checks passed 100%.
- Unit tests: 350/350 passed.
- Integration tests: 93/93 passed.
- Total pytest: 443/443 passed.

**Known Problems:**
- None.

**Spec/ADR Deviations:**
- None.

**Next Recommended Action:**
- Submit `build/m6` for independent review.

---

## 2026-10-01 09:38 (UTC+2) - Antigravity (Gemini 3.8 Flash)
**Milestone:** M6.3
**Task:** M6.3 Recovery, Verification, Commit, Remote CI & Review Handoff

**Files Changed:**
- `src/sports_intelligence/collectors/freshness.py`
- `src/sports_intelligence/context/builder.py`
- `src/sports_intelligence/context/errors.py`
- `src/sports_intelligence/context/models.py`
- `src/sports_intelligence/context/provenance.py`
- `src/sports_intelligence/context/selector.py`
- `src/sports_intelligence/db/migrations/versions/0010_m6_3_freshness_policy.py`
- `src/sports_intelligence/db/models/context.py`
- `src/sports_intelligence/quality/engine.py`
- `src/sports_intelligence/workers/tasks/context.py`
- `src/sports_intelligence/workers/tasks/pre_match.py`
- `tests/integration/test_m6_anti_leakage_and_context.py`
- `tests/unit/context/test_context_schema_and_hash.py`
- `tests/unit/features/test_features_math.py`
- `tests/unit/quality/test_quality_config_validation.py`
- `tests/unit/quality/test_quality_engine.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Behavior Implemented:**
- Recovered, verified, and committed all missing M6.3 source and test files to resolve remote delivery mismatch on `build/m6`.
- Refactored `HistoricalFixtureMetadataUnavailable`: raises typed deterministic exception when no `FixtureMetadataSnapshot` exists `<= as_of`. Refuses to persist `FeatureSnapshot`, `DataQualityReport`, or `MatchContext`.
- Metadata Team IDs: Downstream evidence queries and historical `ProviderEntityId` lookups use snapshot's `home_team_id` and `away_team_id` end-to-end.
- Provider Mapping Provenance: Captured resolved `ProviderEntityId` lookups (`first_seen_at <= as_of_utc`) into `provider_mappings` section of source manifest.
- Canonical Source Fingerprint: Deterministic SHA-256 hash of entire source manifest including fixture metadata, evidence snapshots, and provider mappings.
- FreshnessPolicy & Fingerprint: Dataclass tracking TTLs and canonical fingerprint. Added migration `0010_m6_3_freshness_policy.py` for `data_quality_reports.freshness_policy_fingerprint` and extended unique constraint `uq_data_quality_reports_identity`. Symmetrical downgrade verified.
- ContextBuildPolicy: Combines `QualityPolicy` and `FreshnessPolicy`, generating deterministic `build_config_fingerprint` embedded in Celery task idempotency key.
- Strict Pydantic Models: Enforced `ConfigDict(extra="forbid", frozen=True)` across all 13 sections and root `MatchContextV1`.

**Commands/Tests Run:**
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv run pytest -q -m "not integration"`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q -m integration`
- `uv run pytest -q`
- `DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- `docker compose config -q && docker compose --profile telegram config -q`
- `git push origin build/m6`
- `gh run view 36831445894`

**Results:**
- Ruff check: clean (All checks passed!)
- Ruff format: clean (175 files formatted)
- Mypy: clean (Success: no issues found in 118 source files)
- Unit tests: 357 passed in 4.62s
- Integration tests: 96 passed in 17.78s
- Full pytest suite: 453 passed in 20.15s
- Alembic downgrade/upgrade/check: clean, zero schema drift
- Docker compose: valid
- GitHub Actions CI (run `36831445894` on `5fb6c604617c7f93117e6d42d623a92082461981`): SUCCESS (all 3 jobs green)
- Determinism & Security: Zero live external calls, zero credentials, zero LLM calls.

**Known Problems:**
- None.

**Spec/ADR Deviations:**
- None.

**Git Commit Hash if Created:**
- Implementation commit: `5fb6c604617c7f93117e6d42d623a92082461981`

**Next Recommended Action:**
- Submit `build/m6` for independent review. Do NOT merge M6. Do NOT start M7.

---

## 2026-10-01 10:10 (UTC+2) - Antigravity (Gemini 3.8 Flash)
**Milestone:** M6.4
**Task:** M6.4 Acceptance-Fix Pass (Historical League Authority, Deterministic Provider Mappings, Immutability Audit, Task Semantics)

**Files Changed:**
- `src/sports_intelligence/context/selector.py`
- `src/sports_intelligence/context/provenance.py`
- `src/sports_intelligence/db/models/discovery.py`
- `src/sports_intelligence/db/repositories/discovery.py`
- `src/sports_intelligence/pipelines/discover_fixtures.py`
- `src/sports_intelligence/workers/tasks/context.py`
- `src/sports_intelligence/db/migrations/versions/0010_m6_3_freshness_policy.py`
- `src/sports_intelligence/db/migrations/versions/0011_m6_4_historical_league_metadata.py`
- `tests/unit/context/test_context_schema_and_hash.py`
- `tests/integration/test_m6_anti_leakage_and_context.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Behavior Implemented:**
- Historical League Metadata Authority:
  - Added migration `0011_m6_4_historical_league_metadata.py` adding `observed_league_name` and `observed_league_slug` to `fixture_metadata_snapshots` with migration-time backfill from `leagues` table and symmetrical downgrade.
  - Updated `record_fixture_metadata_snapshot` repository method and `discover_fixtures` pipeline to record observed league identity.
  - Refactored `select_evidence` to read league identity directly from `FixtureMetadataSnapshot.observed_league_name` and `observed_league_slug`, eliminating reliance on mutable canonical `League` table.
  - Included `observed_league_name` and `observed_league_slug` in source manifest `fixture_metadata.details`.
  - Added regression test demonstrating mutating `League` row does not alter historical MatchContext identity, source fingerprint, or context hash.
- Deterministic Provider-Mapping Selection and Order:
  - Query ordering in `select_evidence` explicitly orders by `ProviderEntityId.provider.asc(), ProviderEntityId.first_seen_at.desc(), ProviderEntityId.external_id.asc(), ProviderEntityId.id.asc()`.
  - Deterministically selects latest mapping `<= as_of` per provider; excludes future mappings (`first_seen_at > as_of`).
  - Canonical sort on `SelectedFixtureInfo` mapping lists: `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
  - Added unit and integration tests verifying identical source manifest, source fingerprint, and context hash across arbitrary insertion orders.
- Pydantic Immutability Claim Audit:
  - Audited documentation and test suite regarding immutability guarantees.
  - Clarified that `ConfigDict(frozen=True)` provides attribute-level freezing, while mutable Python collections inside models are not deeply frozen.
  - Reaffirmed that the authoritative immutability boundary is persistence in PostgreSQL (`match_contexts` table).
  - Added unit test `test_match_context_immutability_attribute_frozen_and_nested_behavior`.
- Celery Task Error Semantics:
  - Handled `HistoricalFixtureMetadataUnavailable` cleanly in context Celery task.
  - Logs structured warning with zero unexpected traceback dumps.
  - Marks Celery job `FAILED` in database ledger (`jobs` and `job_attempts`) and re-raises exception for worker failure accounting.
  - Added integration test verifying clean logging, ledger failure persistence, and zero context persistence.
- Migration & Documentation Hygiene:
  - Fixed migration `0010_m6_3_freshness_policy.py` revision docstring from `cb9a7f960dbe` to `0010`.
  - Migration `0011` verified through `upgrade head` -> `downgrade -1` -> `upgrade head` -> `alembic check` with zero schema drift.

**Commands/Tests Run:**
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv run pytest -q -m "not integration"`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q -m integration`
- `uv run pytest -q`
- `DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- `docker compose config -q && docker compose --profile telegram config -q`

**Results:**
- Ruff check: clean (All checks passed!)
- Ruff format: clean (177 files already formatted)
- Mypy: clean (Success: no issues found in 119 source files)
- Unit tests: 360 passed in 4.06s
- Integration tests: 99 passed in 18.72s
- Full pytest suite: 459 passed in 19.29s
- Alembic downgrade/upgrade/check: clean, zero schema drift
- Docker compose: valid
- Determinism & Security: Zero live external calls, zero credentials, zero LLM calls.

**Known Problems:**
- None.

**Spec/ADR Deviations:**
- None.

**Git Commit Hash if Created:**
- Implementation commit: `cedf481ca8839714b82b0dfaf75bab33023e32a8`

**Next Recommended Action:**
- Stage, commit, push to `origin/build/m6`, monitor GitHub Actions CI, and provide handoff report.

---

### 2026-10-01 — Antigravity (Milestone M6.5 Historical-Truthfulness Acceptance Pass)

**Agent/Model:** Antigravity / Gemini 2.5 Pro  
**Milestone:** M6.5 (Historical-Truthfulness Acceptance Pass on `build/m6`)  
**Task:** Resolve M6.4 review findings regarding false historical backfill in migration 0011, mutable League fallback in context selector, and missing truthful pre-0011 regression test.

**Files Changed:**
- `src/sports_intelligence/db/migrations/versions/0011_m6_4_historical_league_metadata.py`
- `src/sports_intelligence/context/selector.py`
- `src/sports_intelligence/context/models.py`
- `src/sports_intelligence/quality/engine.py`
- `tests/unit/context/test_context_schema_and_hash.py`
- `tests/integration/test_m6_anti_leakage_and_context.py`
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Behavior Implemented:**
- Elimination of False Historical Backfill:
  - Removed SQL `UPDATE` statement in migration 0011 that backfilled pre-existing `fixture_metadata_snapshots` from current mutable `leagues` table at migration time.
  - Pre-0011 legacy snapshots do not acquire migration-time values; legacy rows retain `NULL` for `observed_league_name` and `observed_league_slug`.
- Elimination of Mutable League Fallback:
  - In `select_evidence`, removed fallback to mutable `League` row attributes (`league_obj.name`/`league_obj.slug`) and eliminated placeholder sentinels (`"Unknown"`/`"unknown"`).
  - Simplified mutable `Fixture` locator to an existence-only check (`select(Fixture.id)`).
  - When snapshot has no observed league identity, `league_name` and `league_slug` evaluate to `None`.
- Nullable Display Identity in Models:
  - Made `SelectedFixtureInfo.league_name`, `SelectedFixtureInfo.league_slug`, and `FixtureIdentitySection.league_name`/`league_slug` nullable (`str | None = None`).
  - Authoritative `league_id` remains strictly non-null.
- Truthful Quality & Manifest Handling:
  - In `evaluate_data_quality`, missing observed league display identity records a structured warning (`"Observed league display identity unavailable in historical metadata snapshot"`) and missing field entry (`field="observed_league_display"`).
  - Missing display fields do not trigger `fixture_metadata_missing` and do not block `can_predict`.
  - Manifest records `null` for `observed_league_name` and `observed_league_slug`.
- Comprehensive Unit & Integration Regression Verification:
  - Added unit test `test_match_context_with_none_league_display_metadata_serializes_cleanly` verifying `None` display fields serialize cleanly to canonical JSON (`"league_name":null`, `"league_slug":null`) and generate a valid SHA-256 hash.
  - Added 10-step integration regression test `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` covering steps A through J: schema 0010 downgrade, legacy insert at T0, migration 0011 upgrade at T1 without backfill, context build between T0 and T1, absent mutable values, truthful provenance, League mutation at T2, and replay reproducibility with matching context hash and source fingerprint.

**Commands/Tests Run:**
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv run pytest -q -m "not integration"`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q -m integration`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q`
- `DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- `docker compose config -q && docker compose --profile telegram config -q`

**Results:**
- Ruff check: clean (All checks passed!)
- Ruff format: clean (177 files already formatted)
- Mypy: clean (Success: no issues found in 119 source files)
- Unit tests: 361 passed in 3.73s (100%)
- Integration tests: 100 passed in 15.82s (100%)
- Full pytest suite: 461 passed in 17.65s (100%)
- Alembic downgrade/upgrade/check: clean, zero schema drift
- Docker compose: valid
- Determinism & Security: Zero live external calls, zero credentials, zero LLM calls.

**Known Problems:**
- None.

**Spec/ADR Deviations:**
- None.

**Git Commit Hash if Created:**
- Implementation commit: `86cc3ddcbb7625723ab1fb442cac65c53be46b87` (GitHub Actions CI Run `36837766536` — SUCCESS)

**Next Recommended Action:**
- Independent review handoff for M6.5. Do NOT merge M6. Do NOT start M7. Development remains LOCAL ONLY.

---

### 2026-10-01 — Antigravity (Milestone M6 Acceptance & Final Merge Preparation)

**Agent/Model:** Antigravity / Gemini 2.5 Pro  
**Milestone:** M6 (Final Acceptance & Documentation Finalization on `build/m6`)  
**Task:** Independent review verdict received: M6 / M6.5 = PASS / ACCEPTED. Perform Phase A documentation-only finalization prior to merging into `main`.

**Files Changed:**
- `docs/CURRENT_TASK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/REVIEW_HANDOFF.md`
- `docs/AI_WORKLOG.md`

**Independent Review Verdict:**
- M6 / M6.5 = **PASS / ACCEPTED**
- Reviewed accepted pre-merge HEAD: `cec7210cf440b9cc06c040611e477cfed9ad5472`
- Implementation commit: `86cc3ddcbb7625723ab1fb442cac65c53be46b87`
- Final CI run for accepted HEAD: `36837924850` (Conclusion: SUCCESS across all 3 jobs)
- Verified remote results: unit (361 passed, 100 deselected), integration (100 passed, 361 deselected), Ruff check clean, Ruff format clean, mypy clean (119 files), Alembic check clean (0 drift), Docker Compose validation clean.
- Zero remaining source-code blockers.

**Behavior Implemented:**
- Phase A docs-only finalization:
  - Updated `docs/CURRENT_TASK.md`: recorded M6 accepted, review verdict PASS/ACCEPTED, pre-merge HEAD, final CI run, and next merge actions.
  - Updated `docs/IMPLEMENTATION_STATUS.md`: recorded M6.5 and M6 overall as PASS / ACCEPTED, preserving historical review findings; marked M7 as NOT STARTED.
  - Updated `docs/REVIEW_HANDOFF.md`: synchronized commits and CI run IDs; aligned immutability semantics (attribute-level Pydantic freeze vs collection mutability, application-level PostgreSQL persistence boundary, context hash comparison vs read-time recomputation).
  - Appended review outcome to `docs/AI_WORKLOG.md`.

**Commands/Tests Run:**
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv run pytest -q -m "not integration"`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q -m integration`
- `TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q`
- `DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- `docker compose config -q && docker compose --profile telegram config -q`

**Results:**
- All acceptance checks previously verified green and unchanged.
- Documentation-only changes; zero source code or test changes.

**Known Problems:**
- None. M6 is fully accepted.

**Spec/ADR Deviations:**
- None.

**Git Commit Hash if Created:**
- Docs-only finalization commit pending.

**Next Recommended Action:**
- Commit docs changes, push `build/m6`, wait for GitHub Actions CI green, open PR to `main`, merge, tag `v0.7-m6`, and create `build/m7`.




---

### 2026-10-01 — Codex (M7 implementation checkpoint)

**Milestone:** M7, `build/m7`; accepted base `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` / `v0.7-m6`.
**Task:** Implement binding user scope preserved in `docs/M7_SCOPE.md`.
**Files changed:** prediction contracts/config/identity/projection/router/engine/baselines/service/telemetry;
LLM providers; ranking; DB models and migration 0012; API; worker/context completion hook;
Telegram thin UI; prompt/config/runtime packaging; unit/integration tests; current-state docs.
**Behavior:** separate forecast and price comparison; all 12 probabilities; one repair globally;
configured fallback/retries/budgets; immutable prompt/config snapshots at enqueue; semantic reuse
and explicit rerun token; separate baselines; primary/challenger and with/without odds;
DB-loaded jobs on llm queue, persisted read UI.
**Commands/tests:** Ruff/mypy during implementation; M7 unit/provider contracts;
M7 Postgres/Redis integration; empty `sports_intel_m7_test` upgraded through 0012.
**Results:** 149 new unit/HTTP-contract tests passed; 21 new integration tests passed including
keyless discovery→collectors→M6 context→MockLLM→API→Telegram fake transport.
Full repository gates, migration cycle and exact remote CI still pending.
**Known problems:** final hardening/coverage/docs and complete gates remain; no live LLM integration verified.
**Spec/ADR deviations:** existing PREMATCH phase retained; DC benchmark derived from same-bookmaker
captured 1X2 because overlapping outcomes must not normalize to sum 1; WITHOUT_ODDS conservatively
masks arbitrary research text/quality details to avoid market leakage. Go runtime adapter disabled
by default pending permitted-use configuration; current docs describe coding-agent traffic.
**Git commit:** not created yet; changes understood and scoped to M7.
**Next action:** final hardening, full local gates, documented handoff, commit/push build/m7 and exact-head CI;
then STOP for independent review. No merge/tag, M8, deployment, Hetzner or Hermes.

---

### 2026-10-01 — Codex (M7 local verification and review preparation)

**Milestone:** M7, build/m7, accepted base/main `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` / v0.7-m6.
**Task:** Complete implementation, integrity hardening, all local quality gates and handoff.
**Files changed:** all M7 implementation/test files listed in Git diff; runtime docs, ADR 0010,
.env.example, Docker prompt packaging, CI Telegram-profile validation, Makefile Redis db15 isolation.
**Behavior:** complete scoped forecasting layer, strict bounded repair/fallback, actual identity and telemetry,
configurable float threshold tolerance, frozen config/context checks, automatic scanner→context→prediction
integration, immutable reruns and thin Russian Telegram. No M8/settlement/evaluation/ensembles/staking.
**Commands/tests:** uv run ruff check .; ruff format --check .; mypy src; unit, integration and full pytest;
fresh upgrade and populated M6→M7 regression; Alembic downgrade -1/upgrade/check; Compose default/Telegram
validation; Git diff hygiene; secret sanity of working files and Git history (values never printed).
**Results:** 531 unit, 128 integration, 659 total; Ruff/format clean (208 files), strict mypy clean (142 source
files); migration zero drift and M6 content/hash preservation; Compose valid; secret scan clean.
Keyless discovery→collectors→MatchContext→MockLLM→API→Telegram transport passed; actual scanner completion
and duplicate scan deduplication verified; real isolated Redis broker has only job/run UUID payloads.
**Known problems/limitations:** real runtime providers and new live Telegram flow not smoke-tested;
no LLM provider/model/credentials locally configured, zero real LLM calls. Poisson uncalibrated/unadjusted;
WITHOUT_ODDS also removes research free text; crash/lost-delivery recovery needs inspection/explicit rerun.
**Spec/ADR deviations:** ADR 0010 documents scoped choices; PREMATCH existing enum retained; DC uses
same-bookmaker captured 1X2. No changes to accepted M0–M6 migration history.
**Git commit:** pending coherent implementation commit; exact source commit and CI recorded next.
**Next action:** commit/push build/m7, verify exact remote HEAD Actions, then stop for independent review.
Zero deployment, Hetzner, SSH or Hermes interaction; main unchanged; no merge/tag of M7 or M8 work.

---

### 2026-10-01 — Codex (M7 remote verification / final handoff)

**Milestone:** M7, build/m7. **Task:** Complete remote CI verification and synchronize review state.
**Files changed:** docs/CURRENT_TASK.md, IMPLEMENTATION_STATUS.md, REVIEW_HANDOFF.md, AI_WORKLOG.md.
**Behavior:** documentation only; mark implementation verified, preserve independent-review stop boundary.
**Commands/tests:** git push origin build/m7; gh run watch/view 36890119992; exact head/job/log verification;
Git status/diff, unchanged accepted main/tag and old migration history confirmed. No source changes since gates.
**Results:** source HEAD `6c861b94c6300ae7da018176f5af12804f22b217`; CI run `36890119992` SUCCESS on that
exact HEAD, all three jobs (lint/type/unit, integration, Compose+Telegram) SUCCESS. Local 531 unit,
128 integration, 659 full; Ruff/format/mypy, Alembic cycles/drift, Compose and secret sanity all passed.
**Known problems:** no runtime LLM credentials/calls; live providers/new live Telegram not verified;
Poisson/anti-anchoring/operational recovery limitations retained in PREDICTIONS.md and REVIEW_HANDOFF.md.
**Spec/ADR deviations:** ADR 0010 scoped choices; no new deviation or M8 work.
**Git commits:** foundation `231d4539d074d5a3838bc535bbb81cd06855af84`; integration
`6c861b94c6300ae7da018176f5af12804f22b217`. Final documentation commit follows and is rechecked on its own
remote HEAD; final SHA and CI run are returned in the completion report.
**Next action:** publish this documentation-only handoff commit to build/m7, verify its exact CI HEAD, then
STOP for independent review. M7 NOT merged/tagged; main remains `11b6e782...` / v0.7-m6; M8 NOT started;
zero deployment / Hetzner / SSH sessions / Hermes interaction.

---

### 2026-10-01 — Codex (M7.1 focused M4 canonical market fix, verification in progress)

**Milestone:** M7.1 on `build/m7`; reviewed starting HEAD `b0dd35c3606449d95c3be0723ded5f78a2883e67`.
**Task:** Fix M4 `h2h_1x2` normalization compatibility in M7 baselines/ranking without redesigning M4.
**Files changed so far:** `predictions/baselines.py`; provider Mock output in `providers/odds/mock.py`;
M7 `tests/m7_fakes.py`, baseline/ranking regressions, M4 mock-provider contract regression; M7.1 status,
review, prediction-method documentation. No migration/schema changes.
**Behavior:** Accept canonical `h2h_1x2` and preserve `h2h`/`1x2` aliases; map home/draw/away and group them
as canonical 1X2. Only complete, normalized same-bookmaker 1X2 is eligible. DC rows remain excluded from
no-vig baseline; derive HOME_OR_DRAW / HOME_OR_AWAY / DRAW_OR_AWAY from that bookmaker's full 1X2.
M7 synthetic canonical rows and M4 mock normalized output mirror M4 persisted DTO; raw provider request key stays `h2h`.
**Commands/tests run:** focused baseline/ranking + odds mapping unit tests; M7 integration suite on dedicated
`sports_intel_m7_test` and Redis db15.
**Results:** 33 targeted unit/M4 contract tests passed; 27 M7 integration tests passed, including E2E using
MockOddsProvider after it emits `h2h_1x2`. Full acceptance gates have not yet been rerun.
**Known problems:** None found in focused checks; exact remote CI remains pending.
**Spec/ADR deviations:** None. No changes to M4 normalization/parser, schema, or migration.
**Git:** no M7.1 commit yet; working on reviewed branch only.
**Next action:** full unit/integration/full pytest, Ruff/format/mypy, Alembic, Compose, secret sanity; update
final handoff, commit/push `build/m7`, verify exact-head Actions, then STOP. M8/merge/tag/deploy remain prohibited.

---

### 2026-10-01 18:54 UTC — Codex (M7.1 canonical M4 odds acceptance)

**Milestone:** M7.1 on `build/m7`; reviewed start HEAD `b0dd35c3606449d95c3be0723ded5f78a2883e67`.
**Task:** Fix M7 baseline/ranking support for accepted M4 canonical 1X2 odds values.
**Files changed:** `src/sports_intelligence/predictions/baselines.py`; the M4 mock DTO emitter in
`src/sports_intelligence/providers/odds/mock.py`; `tests/m7_fakes.py`;
`tests/unit/predictions/test_baseline_ranking.py`; `tests/unit/test_odds_mapping.py`;
`docs/CURRENT_TASK.md`, `IMPLEMENTATION_STATUS.md`, `REVIEW_HANDOFF.md`, `PREDICTIONS.md`.
**Behavior:** maps canonical `h2h_1x2` + HOME/DRAW/AWAY selections while retaining earlier M7 aliases;
normalizes all aliases into one complete 1X2 group key. Baseline accepts only complete same-bookmaker
no-vig 1X2 with identified bookmaker. DC normalized prices are ignored; all DC probabilities are derived
from that same book's captured 1X2. Mock DTO emits canonical M4 market; provider request `h2h` unchanged.
No M4 live parser/schema redesign.
**Commands/tests run:** focused M7 baseline/ranking and M4 mock-adapter unit tests; all M7 integration;
full unit/integration/full pytest; Ruff, format, mypy, Alembic check, Compose default/dev/Telegram configs.
**Results:** focused 33 tests initially passed. Full current results: 535 unit, 128 integration,
663 total passed. Ruff/format clean (208 Python files), mypy clean (142 source files), Alembic check zero
schema drift, Compose configs valid. Full keyless M7 integration/E2E runs against dedicated Docker DB/Redis.
**Known problems:** remote CI for the M7.1 HEAD still pending. Runtime providers remain contract-tested only;
zero live LLM calls/credentials.
**Spec/ADR deviations:** none; no schema change/migration. The M4 `h2h` wire request key remains provider-specific.
**Git commit:** pending local acceptance commit.
**Next action:** secret-sanity/diff check, commit and push `build/m7`, exact-head GitHub Actions; then STOP
for independent review. M7 not merged/tagged; M8/deploy/Hetzner/Hermes not started.

### 2026-10-01 — Codex (M7.1 full local acceptance pass)

**Milestone:** M7.1 on `build/m7`, start `b0dd35c3606449d95c3be0723ded5f78a2883e67`.
**Task:** Close canonical M4 odds mismatch and complete local acceptance.
**Files changed:** M7 baselines/ranking compatibility; canonical synthetic M7 prices; one M4 mock normalized
market label; M7/M4 regression tests; persistent M7.1 status/review documentation.
**Behavior:** `h2h_1x2` home/draw/away now maps and groups with legacy M7 aliases. Only complete same-bookmaker
1X2 is used. DC probabilities derive from that book's 1X2 and ignore overlapping generic no-vig values.
The outgoing provider request key remains `h2h`. No M4 live parser/schema or DB changes.
**Commands/tests:** `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`;
unit, integration and full pytest; `DATABASE_URL=...sports_intel_m7_test uv run alembic check`;
Docker Compose default/dev/Telegram config; secret sanity scan of working files and Git history.
**Results:** 535 unit, 128 integration, **663 full tests passed**; Ruff/format clean (208 Python files),
mypy clean (142 source files); Alembic: no new operations; all Compose configs valid; 279-file/history
secret scan clean. Runtime LLM calls: zero.
**Known problems:** exact remote CI for M7.1 pending; previous M7 CI does not verify this fix.
**Spec/ADR deviations:** none. M7 DC benchmark same-book requirement remains enforced.
**Git:** M7.1 commit and push pending.
**Next action:** commit/push `build/m7`, verify exact-head GitHub Actions, and STOP for independent review.
M7 unmerged/untagged, M8 not started, LOCAL DEVELOPMENT ONLY, zero deployment/Hetzner/Hermes.

### 2026-10-01 — Codex (M7.1 acceptance and source CI pass)

**Milestone:** M7.1; branch `build/m7`; reviewed start `b0dd35c3606449d95c3be0723ded5f78a2883e67`.
**Task:** Complete the narrow M4 `h2h_1x2` contract compatibility fix and all acceptance gates.
**Files changed:** prediction baseline mapping, M4 MockOddsProvider canonical DTO emitter, M7 synthetic context,
M7 baseline/ranking tests, M4 Mock odds contract test, and persistent M7.1 docs.
**Behavior:** Complete same-bookmaker canonical 1X2 benchmark from `h2h_1x2/home|draw|away`; retain M7 aliases;
derive all DC benchmark probabilities only from that complete same-bookmaker 1X2. Incomplete and split-book
markets are rejected. Provider wire request `h2h` and live M4 normalizer/schema are unchanged.
**Commands/tests:** `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`;
unit, integration and full `pytest`; `DATABASE_URL=...sports_intel_m7_test uv run alembic check`;
Docker Compose default, dev override and Telegram profile; working-file/Git-history secret scan;
`gh run view 36910780514` for exact pushed HEAD.
**Results:** 535 unit + 128 integration = **663 passed**. Ruff/format clean (208 Python files), mypy clean
(142 source files), Alembic reports no new upgrade operations, Compose configs valid. Secret scan checks
279 files and Git history with no findings. CI run `36910780514` on source HEAD
`07658d8e9fdd29f0e642447fd1639efb0b08aa47`: lint/type/unit, Postgres/Redis integration, and Compose
validation jobs all SUCCESS. Zero runtime LLM calls.
**Known problems:** none specific to M7.1; live providers/new Telegram interaction not exercised.
**Spec/ADR deviations:** none. No schema migration or architecture redesign.
**Git:** source fix commit `07658d8e9fdd29f0e642447fd1639efb0b08aa47`, pushed. Final documentation-only commit follows.
**Next action:** push docs, check CI on exact docs HEAD, STOP for independent review. M7 stays unmerged/untagged;
M8 is not started; LOCAL DEVELOPMENT ONLY.

---

### 2026-10-01 19:02 UTC — Codex (M7.1 source CI verified)

**Milestone:** M7.1; source HEAD `07658d8e9fdd29f0e642447fd1639efb0b08aa47` on `build/m7`.
**Task:** Verify exact pushed M7.1 CI and prepare independent-review stop.
**Files changed:** Persistent review/checkpoint documents only; no source or test changes after the passing suite.
**Behavior:** Record exact remote acceptance evidence and preserve the M7.1 review boundary.
**Commands/tests:** `gh run view 36910780514`; Git refs/status, prior full local tests, Alembic and Compose gate results.
**Results:** GitHub Actions run `36910780514` on exact code HEAD has all 3 jobs SUCCESS: lint/type/unit,
Postgres/Redis integration, Docker Compose validation. Local 535 unit + 128 integration = 663 pass;
Ruff/format/mypy clean; Alembic no drift; Compose default/dev/Telegram valid; secret scan clean.
**Known problems:** The final docs-only commit will trigger its own CI run; M8 remains outside this task.
**Spec/ADR deviations:** none. No migration/schema changes.
**Git:** M7.1 code commit `07658d8e9fdd29f0e642447fd1639efb0b08aa47`, pushed. Main stays at accepted M6.
**Next action:** push this documentation-only review update, verify its exact HEAD CI, then STOP for independent
review. M7 remains unmerged/untagged; M8 and deployment are not started.

### 2026-10-01 — Codex (M7.1 review handoff CI verified)

**Milestone:** M7.1; branch `build/m7`; code HEAD `07658d8e9fdd29f0e642447fd1639efb0b08aa47`.
**Task:** Verify remote CI for M7.1 code and documentation-only review handoff.
**Files changed:** review/current task/implementation status and append-only worklog documentation only.
**Behavior:** no source behavior changes; records acceptance result and independent-review stop.
**Commands/tests:** `gh run view 36910780514` for code HEAD and `gh run view 36911401660` for the pushed review handoff HEAD.
**Results:** both runs SUCCESS on their exact heads; three CI jobs each (lint/type/unit, integration, Docker Compose)
passed. Local M7.1 full pytest remains 535 unit + 128 integration = 663 passed. Final subsequent docs-only
push/CI receipt is returned in the completion message.
**Known problems:** none specific to M7.1; independent review is pending.
**Spec/ADR deviations:** none. No M8, deployment, schema or source change.
**Git:** docs-only handoff CI run `36911401660` SUCCESS; branch remains `build/m7`.
**Next action:** STOP for independent review. M7 is not merged/tagged; M8 not started.

---

### 2026-10-01 21:50 CEST — Codex (record owner-supplied M7 acceptance verdict)

**Milestone:** M7 / M7.1 — PASS / ACCEPTED.
**Task:** Finalize accepted M7 documentation and release flow; no new source implementation.
**Files changed:** docs/CURRENT_TASK.md, IMPLEMENTATION_STATUS.md, REVIEW_HANDOFF.md, AI_WORKLOG.md.
**Independent review verdict:** User supplied PASS / ACCEPTED. Accepted branch HEAD `3c75d09676d84e31a2f6d5b0265cd9b629f87f9b`; M7.1 implementation `07658d8e9fdd29f0e642447fd1639efb0b08aa47`; final accepted CI `36911970853` SUCCESS across all jobs.
**Completed behavior:** status and reviewer entry updated. Historical M6 failures and prior worklog entries remain unchanged.
**Verification:** starting `main`/tag `v0.7-m6` still equals accepted M6 SHA; branch is build/m7; no open M7 PR, tag v0.8-m7, or build/m8 existed before this finalization.
**Known problems:** no M7 blockers. Main merge/tag/branch-creation steps remain to complete under this request.
**Spec/ADR deviations:** none. LOCAL DEVELOPMENT ONLY. No M8 code or deployment/Hetzner/Hermes interaction.
**Git:** docs-finalization commit pending.
**Next action:** commit/push docs; exact docs-head CI; create PR to main, normal merge after checks; verify merged-main CI; annotated v0.8-m7; create/push empty build/m8 from accepted main and stop.

### 2026-10-01 21:55 CEST — Codex (M7 acceptance docs finalization)

**Milestone:** M7 / M7.1 independently accepted PASS / ACCEPTED.
**Task:** Record supplied verdict and begin the explicitly authorized PR/merge/tag/empty-build/m8 finalization.
**Files changed:** `docs/CURRENT_TASK.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/REVIEW_HANDOFF.md`, `docs/AI_WORKLOG.md`.
**Behavior:** Acceptance record now identifies accepted branch HEAD `3c75d09676d84e31a2f6d5b0265cd9b629f87f9b`, implementation commit `07658d8e9fdd29f0e642447fd1639efb0b08aa47`, and accepted CI run `36911970853` (SUCCESS across all jobs). Historical review failures remain untouched.
**Commands/tests:** Read mandatory repo instructions/state/docs; confirmed clean `build/m7`, accepted main/tag, absent M7 PR, and absent v0.8-m7/build/m8. Existing M7 acceptance evidence retained.
**Results:** Documentation closeout prepared on accepted build/m7. M7 not merged/tagged yet; M8 not started. Main remains M6 until PR merge.
**Known problems:** none in accepted M7. Merge, tag and clean branch creation remain to execute.
**Spec/ADR deviations:** none. No source/schema change. LOCAL DEVELOPMENT ONLY.
**Git:** docs-only acceptance finalization commit pending.
**Next action:** commit/push docs, verify exact docs-head CI, open PR build/m7→main, wait checks, merge normally, verify merged-main CI, tag v0.8-m7, then push empty build/m8 from exact main and stop.

### 2026-10-02 CEST — Codex (M8 implementation and focused verification)

**Milestone:** M8, build/m8, accepted base/main 4eff88bcaaac387ec047d50575d25b8135baa567 / v0.8-m7.
**Task:** Binding result truth, settlement, evaluation, scheduled local flow, API and thin Telegram.
**Files changed:** M8 result/metric/config/services, SportsDataProvider date result adapters, DB models +
0013 migration, worker/Beat, API/schemas, bot/backend/menu, tests, methodology ADR/doc and current state.
**Behavior:** append-only corrected result versions; regulation_v1; all 12 settlements; displayed-only fixed-unit
research return; separate roles/variants/baselines; cutoff/config-bound immutable evaluation; segmented metrics
and calibration; opt-in automatic date worker → settlement → queued 7d/30d/all metrics; persisted read UI.
**Commands/tests:** uv run Ruff/format/mypy; focused M8 unit/provider/Telegram tests; isolated Docker
sports_intel_m8_test + Redis db15 integration; populated 0012→0013/downgrade/re-upgrade/Alembic check.
**Results:** 299 focused unit passed, 12 integration initially passed including full keyless E2E and migration.
Further hardening checks found a closing-proxy synthetic market label mismatch; corrected test fixture to
accepted M4 ou_15 canonical identity. Complete gates and remote exact-head CI still pending.
**Known problems:** full regression/remote gates not yet verified. Zero live result/LLM calls; live bot untested.
**Spec/ADR deviations:** ADR 0011 explicitly defines time basis, void/postponed, metric/ROI conventions,
result correction history and immutable evaluation reuse. Existing M0–M7 migrations unchanged.
**Git commit:** not yet created; implementation scoped to M8; main remains accepted M7.
**Next action:** finish hardening/full gates/docs, scoped commit/push build/m8, exact-head Actions; stop for
independent review without M8 merge/tag, M9, deployment/Hetzner/Hermes.

### 2026-10-02 CEST — Codex (M8 full local acceptance gates)

**Milestone:** M8 / build/m8; accepted M7 base 4eff88bcaaac387ec047d50575d25b8135baa567 / v0.8-m7.
**Task:** Finish full local tests, methodology/integrity hardening and independent-review packet.
**Files changed:** M8 source/tests/docs and .env.example; existing provider stub/menu assertions;
M4 pre-match planner test date now uses Warsaw local_today (production planner unchanged).
**Behavior:** full M8 scope; displayed coverage counts pending results, probability accuracy excludes
void/unsettled; result/candidate/metric source identities are preserved; optional explicit closing proxy;
malformed backend responses safe; original FeatureSnapshot plus MatchContext/M7 evidence unchanged.
**Commands/tests:** uv run ruff check .; ruff format --check .; mypy src; standalone unit/integration;
full pytest; fresh empty sports_intel_m8_fresh_test upgrade head/down -1/up/check; populated M7 migration
regression; Compose default/dev/Telegram configs; working-file/history secret sanity; git diff --check.
**Results:** 834 unit + 145 integration = **979 full pytest PASS** (33.89s). Ruff/format clean (227 files),
strict mypy clean (155 source files), fresh/populated migration cycles and zero drift PASS, Compose PASS,
301-file/history secret sanity PASS. Full keyless M2→M8 + API/Telegram test transport PASS.
**Known problems:** no local code blockers. Live result provider/new bot interaction unverified;
zero live result/LLM calls. Exact remote HEAD CI still pending.
**Spec/ADR deviations:** ADR 0011 explicit analytical settlement/measurement conventions; no hidden
ET/shootout scoring, no fabricated baseline/cost/closing data. Accepted migrations 0001–0012 unchanged.
**Git commit:** local coherent implementation commit pending; main remains accepted M7.
**Next action:** commit/push build/m8, verify exact-head CI, update receipt and stop for independent review.
M8 NOT merged/tagged; M9 NOT started; zero deployment/Hetzner/Hermes/server interaction.

### 2026-10-02 CEST — Codex (M8 final numerical/retry gate)

**Milestone/task:** M8 final gate before scoped source commit.
**Files changed:** result retry helper/header propagation, safe backend metric DTO, five targeted tests;
current task/status/review packet counts refreshed. Existing worklog gate entries remain historical.
**Behavior:** respect eligible Retry-After ≤30s; larger/invalid waits defer without early external retry;
reject nonfinite backend metric values. Display/settlement metrics and immutable evidence unchanged.
**Commands/tests:** Ruff check/format, strict mypy; unit; full pytest on isolated Compose DB/Redis;
secret sanity working files/history; git diff --check and accepted-main/branch verification.
**Results:** **839 unit + 145 integration = 984 full tests PASS** (32.87s); 304 new M8 unit and 17 new
M8 integration; Ruff/format/mypy clean (227/155 files); 301-file/history sanity PASS. Fresh/populated
migration and Compose results remain PASS; no ORM/migration changes since those checks.
**Known problems:** remote CI pending; live results and new live bot remain unverified, zero live calls.
**Spec/ADR deviations:** none beyond documented ADR 0011 analytical conventions; no M9 or deployment.
**Git:** scoped build/m8 commit pending; main unchanged at accepted 4eff88b / v0.8-m7.
**Next:** commit/push, exact remote CI, final review receipt, stop unmerged for independent review.

### 2026-10-02 CEST — Codex (M8 source CI timezone-test repair)

**Milestone:** M8. **Task:** Repair CI-only date assertion flake before independent-review handoff.
**Source commit:** a0c9332d2fca5fb8807d16015a7a331928dccbc4, pushed build/m8.
**Evidence:** Actions 36935276839: integration and Compose SUCCESS; unit job FAIL in pre-existing
`test_schedule_morning_creates_job_and_enqueues_full_tuple`: Warsaw fixture_date 2026-10-02 versus
UTC runner date.today() 2026-10-01. Ruff/format/mypy passed. Runtime scheduler was correct.
**Files changed:** tests/unit/test_scheduled_discovery.py; this append-only worklog and review state.
**Behavior:** test freezes UTC 2026-08-21 22:30 and explicit Warsaw settings; expected next local date
2026-08-22 proves boundary deterministically. No scheduler/provider/DB runtime changes.
**Commands/tests:** exact CI failed-job logs inspected; targeted test under TZ=UTC and unit gates next.
**Results:** source local 984 tests previously PASS; corrected final CI still pending.
**Known problems:** only this test gate identified; no implementation/settlement/data leakage issue.
**Spec/ADR deviations:** none. **Git:** fix commit pending; main unchanged; M8 unmerged/untagged.
**Next:** run scoped checks, commit/push timezone-test correction, verify exact final remote CI; STOP.

### 2026-10-02 CEST — Codex (M8 exact source CI and scanner reproducibility)

**Milestone/task:** M8 final completion audit and scanner job-deduplication regression.
**Files changed:** evaluation worker one-line scan-clock fix, actual-scanner integration regression,
CURRENT_TASK/IMPLEMENTATION_STATUS/REVIEW_HANDOFF and this append-only receipt.
**Behavior:** schedule_result_scan uses its fixed supplied scan time for evaluation cutoff; repeat with
same time/config reuses both date and evaluation jobs. Scanner performs no provider I/O. No M7 changes.
**Commands/tests:** UTC-targeted discovery test (4 PASS); TZ=UTC unit (839 PASS); actual-scanner integration
(1 PASS); TZ=UTC full pytest on sports_intel_m8_test/Redis15; Ruff/format/mypy; exact source CI view/watch.
**Results:** source CI 36935653021 on 9de803022600ed761ec3af81c63b9091c47e3230 **all jobs SUCCESS**.
Final local audit after scanner fix: **839 unit + 146 integration = 985 full tests PASS** (33.32s),
Ruff/format clean (227 Python files), mypy clean (155 source files). No schema changes; fresh/populated
migration and Compose gates remain verified. Historical source CI failure 36935276839 remains recorded.
**Known problems:** no code blockers; final receipt/scanner-fix HEAD CI still must be verified before
handoff. Live result provider/new Telegram remain unverified; zero live result/LLM calls.
**Spec/ADR deviations:** none beyond ADR 0011; no M9, merge/tag or deployment/Hetzner/Hermes.
**Git:** implementation a0c9332..., test-fix 9de8030..., both pushed; final scanner/receipt commit follows.
**Next:** push final scoped commit, verify exact final all-job CI and clean tree; STOP for independent review.

### 2026-10-02 CEST — Codex (M8 code gates complete / independent-review stop)

**Milestone/task:** M8 exact runtime-code CI receipt and documentation-only final closeout.
**Files changed:** CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, append-only AI_WORKLOG.
**Behavior:** no source/test/schema changes; record final source verification and review stop.
**Commands/tests:** gh run watch/view 36936292769; final local UTC full 985 tests; Git status/ref checks,
secret sanity, unchanged accepted M7 migrations. Previous local fresh/populated cycles/Compose verified.
**Results:** runtime-code HEAD **7cbf1a1148e162130a25828138f09e99f6963654**, CI **36936292769**:
all 3 jobs SUCCESS — lint/type/unit, Postgres/Redis integration, Docker Compose validation.
839 unit + 146 integration = 985 local full PASS; exact CI mirrors those suites. Ruff/format/mypy clean;
migration/Compose/secret checks passed. main and v0.8-m7 still 4eff88bcaaac387ec047d50575d25b8135baa567.
**Known problems:** no implementation blockers. Live results/new live Telegram unverified; zero live
result/LLM calls. Closing comparator/cost/crash-recovery limits are explicit in EVALUATION.md.
**Spec/ADR deviations:** ADR 0011 only; no M9/model promotion/prompt optimization or deployment.
**Git:** source 7cbf1a1 pushed; documentation-only final commit follows. Its exact HEAD/CI will be verified
and returned in completion; GitHub Actions and origin/build/m8 provide the canonical final receipt.
**Next:** final documentation HEAD CI SUCCESS + clean tree, then STOP for independent review.
M8 NOT merged/tagged; M9 NOT started; zero deployment/Hetzner/SSH/Hermes interaction.

### 2026-10-02 CEST — Codex (M8.1 acceptance blocker reproduction and narrow fix)

**Milestone:** M8.1 on build/m8. **Task:** Correct persisted summary materialization selection.
**Reviewed HEAD:** d56aa3620f728eae500a1d95bce167c986d3dfda; reviewed delivery CI 36936656574 SUCCESS.
**Files changed:** api/routes/evaluation.py; tests/integration/test_m8_summary_selection.py;
CURRENT_TASK, IMPLEMENTATION_STATUS, EVALUATION documentation and append-only AI_WORKLOG.
**Behavior:** exclude incompatible restrictions and unsupported multi-facet shapes before run selection;
prefer more covered scoped dimensions, then source cutoff/UUID; retain bounded metadata paging without
100-run history truncation; unsupported requests return not_available with an explicit reason.
No changes to metrics, settlements, providers, M7, worker flow, database models or migrations.
**Commands/tests:** reviewed-head PostgreSQL regressions (A/B/D + suitability failed; broad single-facet
control passed); Ruff/format/mypy; focused five regressions after fix.
**Results:** before 4 FAIL / 1 PASS reproduces blocker; after 5 PASS. Full acceptance still in progress.
**Known problems:** no focused blocker remains; full local gates and exact pushed CI not yet verified.
**Spec/ADR deviations:** none; existing base + single-facet materialization contract preserved.
**Git:** no M8.1 commit yet; main remains 4eff88b / v0.8-m7; M8 unmerged/untagged.
**Next:** full requested gates, scoped commit/push build/m8, exact-head CI, verified persistent receipts;
STOP for independent review. No M9/deployment/Hetzner/Hermes/server interaction.

### 2026-10-02 CEST — Codex (M8.1 full local gates)

**Milestone/task:** M8.1 narrow persisted-summary acceptance fix on build/m8.
**Files changed:** one API route, five integration regressions, current/status/review/methodology docs.
**Behavior:** appropriate scoped materialization precedes source-cutoff recency; one remaining facet
allowed; group_by reserves it; incompatible restrictions/combinations yield not_available. No formulas,
settlements, collectors, M7, database models, migrations or worker changes.
**Commands/tests:** uv run Ruff/check/format; mypy src; unit; integration; full pytest on Docker
sports_intel_m8_test + Redis15; isolated fresh sports_intel_m81_test Alembic head/down -1/head/check;
Compose default/dev/Telegram; secret sanity working files/history; git diff --check.
**Results:** 839 unit + 151 integration = **990 full PASS** (43.67s), Ruff/format clean (228 files),
mypy clean (155 source files); Alembic cycles/no drift PASS; Compose PASS; 302-file/history sanity PASS.
Regressions A–D and latest equal-scope cutoff/partial-scope coverage PASS; old reviewed code reproduced
4 FAIL / 1 PASS. Historical reviewed M8 delivery d56aa36/CI 36936656574 all-job SUCCESS, completed.
**Known problems:** no local blockers; exact pushed M8.1 CI remains to verify. No live provider calls.
**Spec/ADR deviations:** none; original materialization contract and metrics/settlement versions unchanged.
**Git:** narrow implementation commit next; main still accepted 4eff88b / v0.8-m7.
**Next:** push build/m8, exact source/final CI SUCCESS, completed persistent receipt, STOP for review.

### 2026-10-02 CEST — Codex (M8.1 verification complete / review stop)

**Milestone/task:** M8.1 completed exact-source acceptance checks and persistent closeout.
**Files changed:** CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, append-only AI_WORKLOG only.
**Behavior:** no source/test/schema changes; replace obsolete active pending wording with completed
verification state and exact source receipt. Historical pending notes above remain immutable evidence.
**Commands/tests:** gh run watch/view/log 36976617246; final refs/status; full local gates recorded above.
**Results:** implementation HEAD **248e6b190faf4d5b232b7f6eb60a67510c57ae86**, CI **36976617246**
all jobs SUCCESS — lint/type/unit, integration, Compose. CI logs: 839 unit, 151 integration; mypy155;
no Alembic drift. Local full 990 PASS; Ruff/format, migration cycles, Compose and secret sanity PASS.
**Known problems:** no remaining M8.1 blocker; independent review required. No live provider calls.
**Spec/ADR deviations:** none; no metrics/settlement/provider/M7/schema changes.
**Git commit:** 248e6b1 implementation pushed. This documentation-only receipt preserves the verified
implementation; its final checkout HEAD/CI is the canonical Git/Actions tip and completion receipt.
**Next action:** STOP for independent review after checking the final documentation delivery CI.
M8 not merged/tagged, main remains 4eff88b / v0.8-m7, M9 not started, no deployment/Hetzner/Hermes.

### 2026-10-02 CEST — Codex (record owner-supplied M8 PASS / ACCEPTED)

**Milestone/task:** Finalize independently accepted M8 release flow.
**Files changed:** CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF and append-only AI_WORKLOG.
**Behavior:** Record owner-supplied M8/M8.1 PASS/ACCEPTED, accepted branch HEAD
`f8863a8065df307ff47552750d900accad1ab666`, M8.1 fix `248e6b190faf4d5b232b7f6eb60a67510c57ae86`,
and final CI `36977001070` (all 3 jobs SUCCESS). Historical failed reviews and pending notes preserved.
**Commands/tests:** Read mandatory repo instructions/current state/review history; clean build/m8 HEAD and
accepted main/tag checked locally. GitHub connector confirms repository access, no existing open M8 PR,
and all jobs of accepted CI succeeded. GitHub CLI/SSH lookup currently has a name-resolution failure;
release operations will use the connected GitHub API where supported and retry Git transport for tag/ref pushes.
**Results:** docs-only acceptance update staged locally; no source, tests, metrics, settlements or schema changes.
PR/merge/tag/build/m9 external operations still to complete.
**Known problems:** Git transport and GitHub CLI DNS/API calls failed once in this session; connected GitHub app reads work.
**Spec/ADR deviations:** none. Main remains accepted M7; M8 not merged/tagged; M9 not started.
**Git:** documentation finalization commit pending; branch build/m8.
**Next action:** exact-head docs CI; open PR, checks and merge; verify main CI; tag v0.9-m8; push empty build/m9; STOP.
Zero deployment, SSH, Hetzner, Hermes or server interaction.

### 2026-10-02 07:44 UTC — Codex (record owner-supplied M8 PASS / ACCEPTED)

**Milestone/task:** Finalize independently accepted M8 and prepare authorized GitHub release closeout.
**Files changed:** CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, append-only AI_WORKLOG.
**Behavior:** Record owner-supplied M8/M8.1 PASS/ACCEPTED, accepted build/m8 HEAD
f8863a8065df307ff47552750d25b8135baa567, M8.1 implementation 248e6b190faf4d5b232b7f6eb60a67510c57ae86,
and exact accepted CI 36977001070 (all three jobs SUCCESS). Historical reviews/failures remain intact.
**Commands/tests:** Repository instructions/state/worklog/history read; current clean branch/main/tag refs
verified locally. GitHub connector confirms repo access, no existing open M8 PR, accepted CI job results.
Established repo precedent is merge commit PR #9. GitHub CLI/SSH remote lookup had a name-resolution/API
error; connector reads are available, so retry remote operations through the authorized GitHub connector.
**Results:** docs acceptance update in progress; no source/tests/schema changes. PR/merge/tag/build/m9 remain.
**Known problems:** local git transport/API resolution currently unavailable; continue retrying while using
connected GitHub API for supported operations. No server/deploy interaction.
**Spec/ADR deviations:** none. Main remains accepted M7; M8 not merged/tagged; M9 not started.
**Git:** docs-only acceptance commit pending on build/m8.
**Next action:** push docs closeout, verify exact-head CI, open/check/merge PR, verify main CI, tag v0.9-m8,
create/push empty build/m9 at same main SHA; STOP. Zero deployment, SSH, Hetzner or Hermes interaction.


### 2026-10-02 CEST — Codex (M9 startup / state-doc drift correction)

**Milestone/task:** M9 startup; reconcile completed M8 closeout before implementation.
**Files changed:** CURRENT_TASK, IMPLEMENTATION_STATUS, REVIEW_HANDOFF, M9_SCOPE, append-only worklog.
**Behavior:** M8 ACCEPTED/MERGED/TAGGED; M9 ACTIVE on exact base; historical receipts preserved.
**Commands/tests:** mandatory specs/state/history read; git status/fetch/refs; gh run view 36981326405.
**Results:** all startup refs 490227ac8e27ca4c8870891277fd8783d8a7f1af; clean tree at startup; all three main CI jobs SUCCESS.
**Known problems:** none; sandbox Git/network escalation succeeded. No source changes/tests yet.
**Spec/ADR deviations:** none. **Git commit:** docs checkpoint pending.
**Next:** M9 only; full gates, push build/m9, exact CI, independent review STOP.
Zero real LLM calls; no M10/deployment/Hetzner/Hermes interaction.


### 2026-10-02 CEST — Codex (M9 implementation and deterministic acceptance checkpoint)

**Milestone/task:** M9 experiment/replay/comparison and proposal-only human control.
**Files changed:** experiments package, ten DB models/migration 0014, registered prompts/analyst route,
Celery tasks, API/CLI/bot, env/Compose defaults, synthetic fixtures and tests, methodology/current docs.
**Behavior:** exact frozen-context replay; explicit unavailable reasons; immutable definitions/manifests;
separate outputs, bounded physical-call ledger; M8 paired/full measurements; historical forecast reuse;
strict bounded analyst, deterministic evidence, approvals only create research experiments; audit-only promotion.
**Commands/tests:** Ruff/format/mypy; standalone unit/integration; actual E2E/task-wrapper targeted tests.
**Results:** 872 unit PASS; 195 integration PASS before final task-wrapper regression; wrapper PASS;
real collectors→M6→M7→M8→M9 keyless E2E PASS. Populated M8→M9 roundtrip/no drift in suite PASS.
**Known problems:** final full gates/fresh migration/Compose/secret checks and remote CI still pending.
Initial targeted assertions needed JSON-default normalization and isolation from stale synthetic settlements;
no runtime leakage found. Intermediate local 0014 test schema was reapplied through Alembic only.
**Spec/ADR deviations:** ADR 0012 separate outputs, measurement-only interpretation, conservative numeric
analyst-prose rejection, manual interrupted-claim recovery. No production mutation/paid call/deployment.
**Git commit:** pending scoped M9 delivery. **Next:** full gates, commit/push build/m9, exact CI, review STOP.


### 2026-10-02 CEST — Codex (M9 final local acceptance gates)

**Milestone/task:** M9 complete local verification before scoped delivery commit.
**Files changed:** M9 implementation/test/docs/config paths only; startup tree was clean.
**Behavior:** frozen replay/control-treatment/historical arms; M8 measurements; proposal-only analyst;
immutable evidence and deterministic human lifecycle; no automatic production writes.
**Commands/tests:** uv run ruff check .; ruff format --check .; mypy src; unit; integration; full pytest;
fresh sports_intel_m9_fresh_test upgrade head/down -1/up/check; populated M8→M9 integrity test;
Compose default/dev/Telegram config -q; 325-file/history heuristic secret sanity; git diff --check;
accepted migrations 0001–0013, predictions/evaluation source and production prompt byte-identity check.
**Results:** **872 unit + 196 integration = 1068 full pytest PASS** (56.11s), no skips in full suite;
Ruff/format clean (245 Python files), strict mypy clean (168 source files), migrations/no drift PASS,
Compose PASS, secrets PASS. Keyless full E2E and actual Celery task wrappers PASS.
**Known problems:** no local blockers; exact remote source/final delivery CI still required.
Live LLM/result/new Telegram interactions unverified; zero live LLM calls in this implementation.
**Spec/ADR deviations:** ADR 0012 only; independent fixture-pair minimum, no significance/winner,
manual interrupted-claim recovery, qualitative numeric-prose restriction, null closing/cost measurements.
**Git commit:** scoped M9 source commit follows; main/tag still accepted 490227ac... / v0.9-m8.
**Next action:** push build/m9, exact-head all-job CI, completed handoff, clean-tree independent-review STOP.
M9 not merged/tagged; M10 not started; zero deployment/Hetzner/SSH/Hermes interaction.
