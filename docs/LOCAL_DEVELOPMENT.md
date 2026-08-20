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
make up               # docker compose up -d --build (postgres + redis + api)
make logs             # follow api logs
make down             # stop everything (volumes preserved)
```

Hot-reload development container (editable install + bind mount):

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
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

M0 ships the Alembic scaffold with zero revisions; the first real migration
arrives with M1 database models.

## Quality gates

```bash
make check           # lint + typecheck + test
make test            # pytest only
make lint            # ruff check + ruff format --check
make format          # apply ruff formatting
make typecheck       # mypy src
```

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
