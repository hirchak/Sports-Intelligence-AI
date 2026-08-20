# Implementation Status

**Project:** Sports Intelligence AI  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Current milestone:** M1 (+ fix-milestone M1.1) — implemented, awaiting final review  
**Last updated:** 2026-08-20 (DeepSeek V4 Pro via OpenCode)  
**Last known good commit:** see section 11

---

# 1. Current objective

M1 implemented on branch `build/m1`. Awaiting independent review before
merging to `main` and starting M2.

No Hetzner deployment is authorized.

No Hermes access/dependency is authorized.

---

# 2. Completed

## M0 + M0.1 (accepted: independent review verdict PASS)

- Repository scaffold, FastAPI skeleton, config validation, JSON logging,
  Docker stack, Alembic scaffold, CI, docs, ADRs 0001–0005.
- Finalized in `main` via PR #2 (`7000c32`); tag `v0.1-m0` on `8d28138`.
- Repository renamed to `hirchak/Sports-Intelligence-AI`; URLs updated.

## M1 — Core Infrastructure (branch `build/m1`)

- **DB infrastructure**: shared SQLAlchemy 2 `AsyncEngine` +
  `async_sessionmaker` created in the FastAPI lifespan and stored on
  `app.state`; FastAPI session dependency (`get_session`); engine disposed
  on shutdown. `/ready` uses the shared engine (M0.1 technical debt resolved).
- **Redis infrastructure**: shared async Redis client via lifespan;
  `/ready` uses it; closed on shutdown (verified by test).
- **FastAPI lifespan**: creates DB/Redis resources, startup connectivity
  validation (log-only, API stays up when dependencies are down),
  clean shutdown; no global mutable state — everything injected via
  `create_app(settings)`.
- **Celery**: app factory + module-level app; Redis broker `/0` and result
  backend `/1`; JSON serialization, `enable_utc=True`, beat timezone
  `Europe/Warsaw`; queues `control, sports_io, research_io, llm, evaluation,
  notifications`; route patterns for future task modules; one real task
  (`control.ping`); empty beat schedule. No football tasks.
- **Docker Compose**: api + postgres + redis + worker + beat
  (`sports-intel` project, loopback ports, named volumes).
- **Alembic**: first real migration `0001` — `jobs` + `job_attempts`
  (Operations group only; scope proposal: ADR-0006). Verified apply →
  repeat → downgrade → reapply on a fresh database in tests and CI.
- **Tests**: 37 total (34 unit + 3 integration). Integration tests run
  against real Postgres/Redis service containers in CI.
- **CI**: unit job + new integration job (postgres/redis service
  containers) + compose validation; no external sports/LLM APIs.
- MOCK mode remains fully keyless.

## M1.1 — Fix milestone (independent review: PASS WITH FIXES)

Review fixes implemented:

- **Isolated integration database.** Integration tests (including the
  destructive migration cycle) run only against a dedicated
  `sports_intel_test` database: `make test-integration` auto-creates it,
  `TEST_DATABASE_URL` always points at it, CI uses its own ephemeral
  Postgres service database, Redis test traffic uses db `15`. A guard
  (`tests/helpers.py::require_test_database`) refuses any URL whose
  database name does not end with `_test` — loud failure, not a skip.
  Verified: dev DB `sports_intel` table list identical before/after the
  integration suite.
- **Exception-safe lifespan cleanup.** Cleanup moved to `try/finally`
  (`api/resources.py::close_resources`): on any exit (including exceptions)
  both Redis `aclose()` and engine `dispose()` are attempted; a failure of
  one cleanup does not block the other. Tests: exceptional-exit simulation
  proves both resources are closed; unit tests prove failure isolation.

---

# 3. In progress

None. M1 waits for review.

---

# 4. Acceptance tests passed (actually run)

- `uv run pytest -q -m "not integration"` → **41 passed**
- `make test-integration` (isolated `sports_intel_test` DB, local compose
  services) → **3 passed**; dev DB verified unchanged (table snapshot diff)
- Guard check: integration run against dev DB URL → fails loudly with
  `RuntimeError` (as designed)
- `uv run ruff check .` → **All checks passed**
- `uv run ruff format --check .` → **48 files already formatted**
- `uv run mypy src` → **Success: no issues found in 34 source files**
- `docker compose config -q` (+ dev override) → OK
- Docker smoke: all five services up; `/health` 200; `/ready` 200
  (shared resources); worker "ready" with all 6 queues; beat started;
  `control.ping` executed through the broker and succeeded.

---

# 5. External integrations

## Verified live

None. M1 makes no external API calls.

## Mocked / not yet verified

- Sports data provider (interface only, M2)
- Odds provider (interface only, M4)
- Search provider (interface only, M5)
- Runtime LLM providers (interface only, M7)
- Telegram bot (config fields only, M3)

---

# 6. Known issues / blockers

- Docker Desktop (macOS) combined multi-service bake build fails with a
  `x-docker-expose-session-sharedkey` gRPC error; workaround documented in
  `docs/LOCAL_DEVELOPMENT.md` (build services one at a time). Not a repo
  issue — CI on Ubuntu builds fine via direct `docker build`.
- Starlette pinned `<1.0` to keep `httpx`-based TestClient (starlette 1.x
  deprecates httpx in favor of `httpx2`). Revisit on next dependency bump.
- Uvicorn access logs are plain text; application logs are JSON.
- Celery `ping` task has `type: ignore[untyped-decorator]` (celery ships
  without py.typed; mypy overrides treat celery/kombu as untyped).

## Scheduled technical debt (from M0.1)

- ~~M1: `/ready` shared engine/client via lifespan~~ → done in M1.
- **M2:** provider interfaces must not stay on `dict[str, Any]` — introduce
  normalized internal DTO/Pydantic schemas before the first real sports
  adapter.

---

# 7. Architecture/spec deviations

- M0 scope included API/Postgres/Redis/logging skeletons per explicit user
  instruction → ADR-0005.
- Spec `.md` files kept in repository root → ADR-0002.
- Non-standard local host ports 5433/6380 → ADR-0003.
- Validation policy (`extra="ignore"`, `env_ignore_empty`, `NoDecode`) →
  ADR-0004.
- M1 migration scope limited to `jobs`/`job_attempts` → ADR-0006.

---

# 8. Database/migrations

Status:
- migration `0001` applied locally and in CI (fresh DB cycle tested).

Latest migration:
- `0001_create_jobs_and_job_attempts` (jobs, job_attempts)

Local DB preservation required:
- no, until meaningful live test data exists

---

# 9. API/quota status

Provider:
- not selected/verified (open decision, `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`)

Quota telemetry:
- not implemented (M4)

Cache:
- not implemented (M2+)

---

# 10. Current model/runtime configuration

Development lead:
- DeepSeek V4 Pro (this session)

Runtime prediction model:
- not selected empirically

LLM provider routing:
- not implemented (M7)

---

# 11. Current Git state

Branch:
- `build/m1` (M1 + M1.1 work); `main` = `7000c32` (M0 accepted)

Commit:
- M1.1 commit recorded in `docs/REVIEW_HANDOFF.md` after commit

Working tree:
- clean before M1.1 commit

---

# 12. Next action

1. Final independent review of M1.1 (see `docs/REVIEW_HANDOFF.md`).
2. After acceptance: merge `build/m1` into `main`.
3. Only then start M2 with explicit user approval.

---

# 13. Reviewer notes

A reviewer should start by reading:

1. `AGENTS.md`
2. this file
3. `docs/CURRENT_TASK.md`
4. `docs/REVIEW_HANDOFF.md`
5. relevant specification
6. Git diff `main..build/m1`
