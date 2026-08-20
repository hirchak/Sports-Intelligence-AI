# Sports Intelligence AI

Private football forecasting platform: modular, reproducible, measurement-first.

Current phase: **LOCAL DEVELOPMENT ONLY** (no server deployment, no Hermes dependency).

## Status

- Milestone: **M0 — complete, pending review** (`build/m0` branch)
- See `docs/IMPLEMENTATION_STATUS.md` for the canonical state.

## What this is

A forecasting laboratory, not a "chatbot that guesses scores":

- raw data is separated from interpretation;
- deterministic features are separated from LLM reasoning;
- market odds are separated from model probabilities;
- every prediction is timestamped and reproducible;
- accuracy is evaluated honestly (Brier, log loss, calibration);
- the system can abstain when data quality is insufficient.

Authoritative specifications live in the repository root (`00_MASTER_TECHNICAL_SPEC.md`,
`07_…`–`18_…`). See `README_EXECUTION_ORDER.md` for the document map.

## Repository layout

```text
src/sports_intelligence/   application code (src layout)
  api/                     FastAPI control API (M0: /health, /ready)
  core/                    config, structured logging, time, ids
  db/                      async session factory, Alembic migrations
  providers/               provider interfaces (Protocols, no impl yet)
  schemas/                 Pydantic response models
  bot/ domain/ features/ pipelines/ ranking/ research/ workers/
                           reserved packages for future milestones
tests/                     unit / integration / contract / fixtures
docs/                      architecture, ADRs, dev/deploy/security docs
config/                    sample league/market config (future milestones)
prompts/                   versioned LLM prompts (future milestones)
```

## Quick start

Prerequisites: Docker (with Compose), `uv`.

```bash
git clone git@github.com:hirchak/-.git sports-intelligence
cd sports-intelligence
cp .env.example .env                 # safe MOCK defaults, no real keys needed
docker compose up -d --build         # postgres + redis + api
curl http://127.0.0.1:8000/health    # -> {"status": "ok", ...}
curl http://127.0.0.1:8000/ready     # -> 200 when DB+Redis are up
```

Alternatively: `make bootstrap && make up`.

Host-side ports (loopback only): Postgres 5433, Redis 6380, API 8000.

## Local development

```bash
uv sync --dev                # install locked dependencies
make check                   # ruff + mypy + pytest
make migrate                 # alembic upgrade head (inside api container)
make dev                     # stack up + follow api logs
```

Dev mode with hot reload:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

See `docs/LOCAL_DEVELOPMENT.md` for details.

## Runtime modes

| Mode         | Purpose                        | External keys required |
|--------------|--------------------------------|------------------------|
| `mock`       | offline, deterministic, CI     | none                   |
| `sandbox`    | real APIs, limited fixtures    | yes                    |
| `live_local` | full local scheduler           | yes                    |

Set via `APP_ENV`. In non-mock modes, startup fails fast if a configured
provider has no API key.

## Testing / quality gates

```bash
uv run pytest -q        # unit + integration tests
uv run ruff check .     # lint
uv run ruff format --check .
uv run mypy src         # strict type checking
```

CI runs the same gates on every push/PR (`.github/workflows/ci.yml`).

## Documentation

- `docs/ARCHITECTURE.md` — boundaries and data flow
- `docs/LOCAL_DEVELOPMENT.md` — local workflow details
- `docs/DATA_MODEL.md` — database plan (models arrive in M1)
- `docs/PIPELINES.md` — pipeline plan (implementation arrives M2+)
- `docs/TELEGRAM.md` — bot plan (implementation arrives M3)
- `docs/DEPLOYMENT.md` — deployment status (NOT authorized yet)
- `docs/SECURITY.md` — security requirements
- `docs/adr/` — architecture decision records

## Milestones

M0 (this repo state) → M1 core infra → M2 sports provider/fixtures →
M3 Telegram → M4 match collection → M5 research → M6 features/context →
M7 prediction → M8 settlement/evaluation → M9 improvements/experiments →
M10 production readiness. See `00_MASTER_TECHNICAL_SPEC.md` §36.

## Rules for AI agents

Read `AGENTS.md` before any session. State files:
`docs/IMPLEMENTATION_STATUS.md`, `docs/CURRENT_TASK.md`, `docs/AI_WORKLOG.md`,
`docs/REVIEW_HANDOFF.md`.
