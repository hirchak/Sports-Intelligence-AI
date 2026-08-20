# Implementation Status

**Project:** Sports Intelligence AI  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Current milestone:** M0 — implemented, awaiting review  
**Last updated:** 2026-08-20 (DeepSeek V4 Pro via OpenCode)  
**Last known good commit:** see section 11

---

# 1. Current objective

M0 implemented on branch `build/m0`. Awaiting independent review before
merging to `main` and starting M1.

No Hetzner deployment is authorized.

No Hermes access/dependency is authorized.

---

# 2. Completed

## Pre-M0

- Specification pack prepared.
- Project architecture defined.
- Local-first development policy defined.
- Git/AI control policy defined.

## M0 — Architecture and repository (branch `build/m0`)

- Git repository initialized; spec pack committed to `main`;
  milestone work on `build/m0` (per `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`).
- Python project scaffold: `pyproject.toml` (hatchling, src layout,
  package `sports_intelligence`, Python 3.12), `uv.lock` committed,
  `.python-version` pinned to 3.12.
- FastAPI skeleton: app factory + `GET /health` + `GET /ready`
  (DB `SELECT 1` + Redis ping; 503 when dependencies down).
- Configuration: pydantic-settings `Settings` with `APP_ENV`
  (`mock|sandbox|live_local`), comma-separated Telegram user IDs,
  startup validation of provider keys in non-mock modes, `extra="forbid"`.
- Logging foundation: structured JSON formatter, context fields
  (correlation/job/fixture/run IDs), unit-tested.
- Mock mode: full stack runs with zero external API keys (`APP_ENV=mock`).
- Docker: multi-stage `Dockerfile` (production + development targets,
  non-root user), `compose.yaml` (project `sports-intel`: postgres 16,
  redis 7, api; named volumes; loopback ports 5433/6380/8000),
  `compose.dev.yaml`, `.dockerignore`.
- Alembic scaffold: `alembic.ini` + async `env.py` wired to settings;
  verified against local Postgres (`upgrade head` exit 0, `alembic_version`
  table created; zero revisions in M0).
- CI skeleton: GitHub Actions (`uv sync --frozen`, ruff, mypy, pytest,
  compose config validation).
- Documentation: `README.md`, `docs/ARCHITECTURE.md`,
  `docs/LOCAL_DEVELOPMENT.md`, `docs/DATA_MODEL.md`, `docs/PIPELINES.md`,
  `docs/TELEGRAM.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`,
  ADRs 0001–0005.
- Test structure: `tests/unit`, `tests/integration`, `tests/contract`,
  `tests/fixtures`; 17 tests.
- Git hygiene: `.gitignore`, `.env.example` (placeholders only),
  `Makefile`, `opencode.json.example`.

---

# 3. In progress

None. M0 waits for review.

---

# 4. Acceptance tests passed (actually run)

- `uv run pytest -q` → **17 passed** (Python 3.12.14)
- `uv run ruff check .` → **All checks passed**
- `uv run ruff format --check .` → **31 files already formatted**
- `uv run mypy src` → **Success: no issues found in 25 source files**
- `docker compose config -q` → OK; dev override OK
- `docker compose up -d --build` → postgres/redis/api all **healthy**
- `GET /health` → 200 `{"status":"ok","service":"sports-intelligence"}`
- `GET /ready` → 200 `{"status":"ready","checks":{"database":"ok","redis":"ok"}}`
- `alembic upgrade head` / `current` / `heads` inside api container → exit 0

---

# 5. External integrations

## Verified live

None. M0 makes no external API calls.

## Mocked / not yet verified

- Sports data provider (interface only, M2)
- Odds provider (interface only, M4)
- Search provider (interface only, M5)
- Runtime LLM providers (interface only, M7)
- Telegram bot (config fields only, M3)

---

# 6. Known issues / blockers

- Starlette pinned `<1.0` to keep `httpx`-based TestClient (starlette 1.x
  deprecates httpx in favor of `httpx2`). Revisit on next dependency bump.
- Uvicorn access logs are plain text; application logs are JSON. Unification
  is a minor M1 task.
- CI workflow exists but its first GitHub run happens only after push;
  status to be confirmed in the worklog.

---

# 7. Architecture/spec deviations

- M0 scope includes API/Postgres/Redis/logging skeletons (master spec
  assigned them to M1) per explicit user instruction → ADR-0005.
- Spec `.md` files kept in repository root → ADR-0002.
- Non-standard local host ports 5433/6380 → ADR-0003.
- `Settings` does not require `TELEGRAM_BOT_TOKEN` outside mock mode in M0;
  the bot process will validate its own config in M3 → ADR-0004.

---

# 8. Database/migrations

Status:
- Alembic scaffold configured and verified; no models, no revisions (M1).

Latest migration:
- none

Local DB preservation required:
- no, until meaningful live test data exists

---

# 9. API/quota status

Provider:
- not selected/verified (open decision, `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`)

Quota telemetry:
- not implemented (M4)

Cache:
- not implemented (M1+)

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
- `build/m0` (M0 work); `main` (spec pack only)

Commit:
- M0 commit hash — recorded in `docs/REVIEW_HANDOFF.md` after commit

Working tree:
- clean before M0 commit

---

# 12. Next action

1. Independent review of M0 (see `docs/REVIEW_HANDOFF.md`).
2. After acceptance: merge `build/m0` into `main`.
3. Only then start M1 with explicit user approval.

---

# 13. Reviewer notes

A reviewer should start by reading:

1. `AGENTS.md`
2. this file
3. `docs/CURRENT_TASK.md`
4. `docs/REVIEW_HANDOFF.md`
5. relevant specification
6. Git diff `main..build/m0`
