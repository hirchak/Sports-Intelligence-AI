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
- commit: [pending commit]

**Next action**
- Commit and push to origin/build/m4.
- Verify CI run status.
- Final independent review handoff.


