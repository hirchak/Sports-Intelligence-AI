# Local Development

LOCAL DEVELOPMENT ONLY. Use a local Docker Unix socket. No remote Docker context/SSH/server operations.
Prerequisites: Git, `uv`, Docker with Compose >=2.24.4. Python 3.12 is installed by uv.

## Bootstrap

From a clean checkout, follow README: copy `.env.example` to `.env`, run `make bootstrap`.
The script never overwrites an env file or deletes a volume. It performs locked install, serial builds,
Postgres/Redis startup, `alembic upgrade head`, `scripts/seed_leagues.py`, API/worker/beat start, health and
readiness probes and Telegram Compose validation. Serial build avoids the historical Desktop bake bug.
The application env reaches all application containers; DB/broker URLs are overridden to Docker service DNS.

```bash
make up
make migrate
make seed
make logs
make logs-worker
make logs-beat
make down                      # volumes preserved
```

No reset/drop/down -v is part of bootstrap. Preserve source/evidence before any explicitly approved reset.

## Isolated readiness reproduction

Use a disposable clean local checkout/worktree of the reviewed commit. Create `.env` from the example.
Choose a separate project and unused loopback ports, for example:

```bash
export COMPOSE_PROJECT_NAME=sports-m10-check
export POSTGRES_DB=sports_intel_acceptance_test
export POSTGRES_PORT=15433 REDIS_PORT=16380 API_PORT=18000
make bootstrap
export TEST_DATABASE_URL=postgresql+asyncpg://sports:sports_dev_password@localhost:15433/sports_intel_acceptance_test
export TEST_REDIS_URL=redis://localhost:16380/15
make acceptance-mock
```

These credentials are public MOCK development defaults, never production credentials. Host tools require
host URLs matching the chosen ports; Compose uses internal service names. Create a **different** *_test DB
for full destructive suites, keeping any retained runtime acceptance population separate:

```bash
docker compose exec -T sports-postgres createdb -U sports sports_intel_full_test
# Set TEST_DATABASE_URL to that database before full/integration pytest.
uv run pytest -q -m 'not integration'
uv run pytest -q -m integration
uv run pytest -q
```

Tests refuse non-*_test databases. Redis15 is disposable and must never be a live broker.
Do not run overlapping integration suites against the same DB/Redis. M10's fixture cleans dependent
prediction/experiment rows before older collector fixtures; optional `M10_KEEP_RUNTIME_DATA=1` explicitly
retains the disposable acceptance population for runtime restart checks.

Native restore during the complete E2E:

```bash
M10_BACKUP_PROJECT=sports-m10-check \
M10_BACKUP_DATABASE=sports_intel_acceptance_test \
APP_ENV_FILE=.env M10_REPORT_PATH=/tmp/sports-m10-e2e.json \
M10_KEEP_RUNTIME_DATA=1 uv run pytest -q \
  tests/integration/test_m10_acceptance.py::test_complete_v1_no_network_reproducible_redis_loss_and_restore
uv run python scripts/runtime_acceptance.py --project sports-m10-check --env-file .env --base-url http://127.0.0.1:18000
```

The runtime test allows mutations only of `sports-m10-*` projects on a local Unix socket and loopback API.
It restarts API/worker/beat during queued prediction, tests Redis/Postgres outages, checks original truth,
and measures twelve keyless mock reruns. It restores service availability on failure and never drops volumes.

## Modes and provider configuration

MOCK: configured mocks, no sports/search/LLM keys; optional actual Telegram uses its own explicit token.
SANDBOX/LIVE_LOCAL: real configured providers, no automatic mock fallback. Empty optional search/odds
means disabled. Model identities and physical-call budgets live in `config/llm.yaml`; preserve frozen routes.
`config/leagues.yaml` starts disabled; mock demo has explicit provider mappings. Bump its version for semantic
changes. `SPORTS_PROVIDER=api_football`, `ODDS_PROVIDER=the_odds_api`, `SEARCH_PROVIDER=tavily` require keys.

Scheduling is explicitly configurable: `SCHEDULER_ENABLED`, discovery hours/minutes,
`SCHEDULER_PRE_MATCH_SCAN_ENABLED`, `PREDICTION_AUTO_ENABLED`, `RESULT_SCAN_ENABLED`,
`IMPROVEMENT_SCHEDULE_ENABLED` and `IMPROVEMENT_SCHEDULE_DAY_OF_WEEK/HOUR/MINUTE`.
All automatic gates are disabled by default; weekly default remains Monday09:00. Optional services degrade as documented
in PIPELINES/PREDICTIONS/EVALUATION/EXPERIMENTS. Live experiments/analyst require their separate opt-ins.

## Telegram

Use ignored env credentials, never chat-pasted keys. Set `TELEGRAM_BOT_TOKEN` and positive
`TELEGRAM_ALLOWED_USER_IDS`; empty allowlist refuses startup and access middleware denies unknown users.
`make telegram-up` starts long polling. Avoid running two polling instances with the same token.
`docker compose --profile telegram config -q` validates topology without connecting to Telegram.
Test transport needs no token/network. Live smoke is separate and requires explicit authorization.

## Development and checks

`docker compose -f compose.yaml -f compose.dev.yaml up --build` enables local reload; never combine it
with the production example. Run `make lint`, `make typecheck`, `make test`, `make security-check`.
CI installs `uv sync --frozen --dev`, runs unit/integration/migrations and all Compose validations, keyless.
Use `make lock` only when changing dependencies; commit `uv.lock`. API `/health` checks the process;
`/ready` returns 503 if DB/Redis is unavailable. Queue checks/runbooks are in OPERATIONS.
