# Local Development

## Prerequisites

- Docker (with Compose v2)
- `uv` (installs its own Python 3.12)

## One-time bootstrap

```bash
git clone git@github.com:hirchak/Sports-Intelligence-AI.git sports-intelligence
cd sports-intelligence
make bootstrap        # cp .env.example .env; start postgres + redis
```

`.env.example` is a working MOCK configuration: no external API keys required.

## Starting the stack

```bash
make up               # docker compose up -d --build (api + postgres + redis + worker + beat)
make logs             # follow api logs
make logs-worker      # follow worker logs
make logs-beat        # follow beat logs
make down             # stop everything (volumes preserved)
```

Hot-reload development container (editable install + bind mount):

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Troubleshooting note: on some Docker Desktop versions the combined
multi-service bake build fails with a `x-docker-expose-session-sharedkey`
gRPC error. Workaround — build services one at a time:

```bash
docker compose build sports-api
docker compose build sports-worker
docker compose build sports-beat
docker compose up -d
```

## Celery

```bash
docker compose logs sports-worker    # worker consumes all 6 queues
docker compose logs sports-beat      # scheduler (no schedules in M1)

# send the infrastructure ping task through the broker:
docker compose exec sports-worker \
  celery -A sports_intelligence.workers.celery_app call control.ping --args='["smoke"]'
```

## Ports (loopback only)

| Service  | Host port | Container port |
|----------|-----------|----------------|
| Postgres | 5433      | 5432           |
| Redis    | 6380      | 6379           |
| API      | 8000      | 8000           |

## Health checks

```bash
curl http://127.0.0.1:8000/health   # process alive
curl http://127.0.0.1:8000/ready    # DB + Redis reachable (503 otherwise)
```

## Connection URLs

- Host-side (local tools): `DATABASE_URL` / `REDIS_URL` from `.env`
  (point at localhost:5433 / localhost:6380).
- Inside the api container they are overridden by `compose.yaml` to
  `sports-postgres:5432` / `sports-redis:6379`.

## Migrations

```bash
make migrate         # alembic upgrade head inside the api container
```

M1 ships migration `0001` (`jobs` + `job_attempts`, see ADR-0006). Applied
to a fresh database, downgrade/upgrade is exercised in CI.

## Fixture discovery (M2)

Two provider modes (`SPORTS_PROVIDER` in `.env`):

- `mock` (default): recorded, sanitized API-Football-shaped responses.
  No API key. Demo config with a league enabled:
  `config/leagues.mock.yaml`.
- `api_football`: real API. Requires `SPORTS_API_KEY` in `.env`.

Leagues are configured in YAML (`LEAGUES_CONFIG_PATH`, default
`config/leagues.yaml` — all leagues disabled by default so no quota is
spent accidentally). `provider_ids` are explicit per provider (`mock`
and/or `api_football`); discovery resolves IDs only for the CURRENT
provider and makes zero external calls when no enabled league exists.
Seed league rows into the DB with `make seed`.

Manual discovery (bounded: one API request per date):

```bash
curl -X POST http://127.0.0.1:8000/v1/jobs/discover \
  -H "Content-Type: application/json" -d '{"date": "2026-08-21"}'
curl "http://127.0.0.1:8000/v1/fixtures?date=2026-08-21"
curl "http://127.0.0.1:8000/v1/fixtures?date=2026-08-21&league=premier-league"
```

The handler enqueues a Celery job (`sports.discover_fixtures` on
`sports_io`); repeated POSTs for the same identity reuse the same job and
do not enqueue again. Job identity per `09` spec:

```text
discover:{provider}:{date}:v{league_config_version}:{timezone}
```

Rule: any semantic change to `config/leagues.yaml` MUST bump `version`
(the version is the canonical identity mechanism — never list enabled
leagues in the key). Changing `APP_TIMEZONE` likewise creates a distinct
discovery identity. There is no automatic schedule in M2 — quota is only
spent when you explicitly POST a discovery job.

## Quality gates

```bash
make check           # lint + typecheck + unit tests
make test            # pytest unit (no external services)
make test-integration  # pytest integration against the isolated test DB
make lint            # ruff check + ruff format --check
make format          # apply ruff formatting
make typecheck       # mypy src
```

## Test database isolation

Integration tests are destructive by design (the migration test runs
`alembic downgrade base` + reapply). They must never touch the development
database:

- `make test-integration` auto-creates and uses the dedicated
  `sports_intel_test` database on the local Postgres (and Redis db `15`).
- `TEST_DATABASE_URL` must always point at a database whose name ends with
  `_test`; a guard in `tests/helpers.py` refuses to run integration tests
  against any other database (loud `RuntimeError`, not a silent skip).
- The dev database `sports_intel` is never downgraded or dropped by tests.
- CI uses its own ephemeral Postgres service container with
  `sports_intel_test`, so nothing shared is touched there either.

## Dependency management

```bash
make lock            # regenerate uv.lock after editing pyproject.toml
```

`uv.lock` is committed; CI installs with `uv sync --frozen`.

## Runtime modes

`APP_ENV=mock` (default) — offline, deterministic, no keys.
`sandbox` / `live_local` — real APIs; startup fails if a configured provider
has no key (see ADR-0004). Provider integrations arrive in M2+.

## Troubleshooting

- `docker compose config -q` — validate compose files.
- `docker compose logs sports-postgres` — DB problems.
- Port conflict: change host-side ports in `compose.yaml` (container ports
  must stay standard).
- Reset local state: `docker compose down -v` destroys volumes
  (safe during M0/M1: no valuable data yet).
