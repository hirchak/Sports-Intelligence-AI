# Sports Intelligence AI

Private football forecasting laboratory, with reproducible evidence and deterministic measurement.
**LOCAL DEVELOPMENT ONLY. No deployment, server access or Hermes interaction is authorized.**

M0–M9 independently accepted. M9: PR #11, main `03789b7b7b4af2179271a7797faa754d48ad0d0d`,
annotated `v0.10-m9`. M10 prepares local operational readiness; it stops for independent review,
without merge/tag. Current authority: [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md).

## Bootstrap from repository sources

Prerequisites: local Docker Desktop/Engine with Compose >=2.24.4, `uv`, Git.

```bash
git clone https://github.com/hirchak/Sports-Intelligence-AI.git sports-intelligence
cd sports-intelligence
cp .env.example .env
make bootstrap
```

`make bootstrap` installs locked dependencies, builds production images serially, starts fresh or existing
PostgreSQL/Redis, upgrades Alembic to head, seeds configured leagues, starts API/worker/beat, verifies
`/health` and `/ready`, and validates the optional Telegram profile. Existing env/volumes are preserved.
The default MOCK config requires no credentials; schedules and live experiments are disabled.
Leagues default disabled to conserve quota; use `LEAGUES_CONFIG_PATH=config/leagues.mock.yaml` for demo discovery.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
make down                 # preserves volumes
make up                   # builds/starts the local stack
```

Ports bind loopback: API 8000, PostgreSQL 5433, Redis 6380. Change `API_PORT`, `POSTGRES_PORT`,
`REDIS_PORT` and corresponding host URLs in your local env when running another project.
See [LOCAL_DEVELOPMENT](docs/LOCAL_DEVELOPMENT.md) for isolated acceptance and Telegram setup.

## Verification

```bash
make check                # Ruff, format, mypy, unit
make test-integration     # dedicated *_test PostgreSQL, Redis15
make acceptance-mock      # supply TEST_DATABASE_URL / TEST_REDIS_URL, both isolated
make security-check       # heuristic history/known-secret sanity, no values printed
make compose-safety       # production-like private topology, no containers started
make backup-verify        # native compressed dump + disposable restore verification
```

Full keyless v1 acceptance includes discovery, sports/odds/research, data quality/features/context,
MockLLM, all probabilities and ranking, Telegram test transport, results, settlement, evaluation,
frozen M9 replay and a human-gated proposal. External HTTP transport is explicitly forbidden in that test.
Test integrations never imply live provider acceptance or forecasting quality.

## Runtime and layout

- `src/sports_intelligence/api`, `bot`: private control plane and thin allowlisted Russian Telegram UI.
- `collectors`, `providers`, `research`: batching/freshness/coalescing/quota, normalized immutable evidence.
- `features`, `quality`, `context`: deterministic, point-in-time MatchContext with source/hash identities.
- `predictions`, `ranking`: configurable routes, bounded retries/repair/budgets; math outside the LLM.
- `evaluation`, `experiments`: deterministic result truth/measurement, frozen replay, proposal-only improvement.
- `db`, `workers`: PostgreSQL/Alembic, Redis/Celery/Beat; six named queues.
- `scripts`, `config`, `prompts`, `tests`, `docs`: reproducible operations and versioned contracts.

`APP_ENV=mock` is keyless. `sandbox`/`live_local` require configured provider credentials and reject
implicit mock substitution. Secrets stay in ignored local env files. The API is private and has no
public authentication platform; do not publish it. Telegram requires a token and positive user-ID allowlist.
Production-like topology removes host ports; `PRODUCTION_LIKE=true` refuses DEBUG and hides OpenAPI.

## Documentation

- [ARCHITECTURE](docs/ARCHITECTURE.md), [DATA_MODEL](docs/DATA_MODEL.md), [PIPELINES](docs/PIPELINES.md)
- [TELEGRAM](docs/TELEGRAM.md), [PREDICTIONS](docs/PREDICTIONS.md), [EVALUATION](docs/EVALUATION.md), [EXPERIMENTS](docs/EXPERIMENTS.md)
- [OPERATIONS](docs/OPERATIONS.md), [BACKUP_RESTORE](docs/BACKUP_RESTORE.md), [SECURITY](docs/SECURITY.md)
- [PRODUCTION_READINESS](docs/PRODUCTION_READINESS.md), [M10 acceptance](docs/M10_ACCEPTANCE_REPORT.md)
- [DEPLOYMENT](docs/DEPLOYMENT.md): future only, explicit owner authorization required
- [ADRs](docs/adr/), [specification map](README_EXECUTION_ORDER.md), [binding M10 scope](docs/M10_SCOPE.md)

Read `AGENTS.md` and current state/task/handoff before coding. Historical review failures and delivery
receipts remain in the append-only [AI_WORKLOG](docs/AI_WORKLOG.md) and clearly marked history snapshots.
