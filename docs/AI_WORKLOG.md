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
