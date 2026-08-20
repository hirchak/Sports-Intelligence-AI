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
- commit: recorded after commit (see REVIEW_HANDOFF)

**Next action**
- Independent M0 review; merge `build/m0` → `main` after acceptance;
  then M1 only with explicit user approval.
