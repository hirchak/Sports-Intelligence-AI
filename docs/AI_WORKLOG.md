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
