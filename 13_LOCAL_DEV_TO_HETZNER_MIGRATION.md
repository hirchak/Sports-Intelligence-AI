# Local Development to Hetzner Migration
## Development Lifecycle and Data Movement

The project should be built and validated locally before server deployment.

---

# 1. Local topology

Run with Docker Compose:

```text
sports-api
sports-worker
sports-beat
sports-bot
sports-postgres
sports-redis
```

Optional dev-only:

```text
adminer/pgadmin (only if useful, not required)
```

No Hermes dependency locally.

---

# 2. What lives on the laptop?

## Git-controlled

- Python source;
- Dockerfiles;
- Compose;
- migrations;
- prompts;
- config templates;
- tests;
- documentation.

## Local only

- `.env`;
- PostgreSQL Docker volume;
- Redis volume/cache;
- logs;
- API tokens.

The DB can be deleted/rebuilt during early development if seed/mock data exists.

---

# 3. Local modes

Implement three modes.

## MOCK

No paid/external dependencies required.

Uses:
- recorded sports API fixtures;
- mock odds;
- mock search;
- mock LLM.

Purpose:
- deterministic tests;
- CI.

## SANDBOX

Real APIs but limited leagues/fixtures.

Purpose:
- integration validation;
- quota-safe testing.

## LIVE_LOCAL

Runs normal scheduler locally.

Purpose:
- multi-day real behavior before deployment.

Mode is explicit in config.

---

# 4. Bootstrap

A clean developer machine should be able to run something close to:

```bash
git clone ...
cp .env.example .env
docker compose up -d postgres redis
<run migrations>
<seed leagues>
docker compose up
```

Create `make` or task commands such as:

```text
make dev
make test
make lint
make migrate
make seed
make e2e
make backup
```

Exact command names may vary.

---

# 5. Local DB growth

Use bounded scope during testing.

For example:
- 2 leagues;
- several days;
- limited research;
- limited odds snapshots.

Database growth should be measured, not guessed.

Add an admin/report command:

```text
db storage report
```

that reports largest tables and row counts.

---

# 6. GitHub workflow

Do not push database files.

Do push:

- all migrations;
- fixture samples that are intentionally anonymized/non-secret;
- small provider contract JSON fixtures;
- docs.

Recorded test fixtures should be small enough for Git.

---

# 7. Pre-deployment freeze

Before first Hetzner deployment:

- local acceptance tests pass;
- independent audit passes;
- Git working tree clean;
- known-good commit/tag created;
- `.env.example` complete;
- production secrets prepared separately;
- database migration decision made:
  - start fresh; or
  - migrate local history.

---

# 8. Option A — start production fresh

Recommended if local data is only test data.

Flow:

```text
clone repo
create production .env
start Postgres/Redis
run migrations
seed leagues
start services
```

Cleanest approach.

---

# 9. Option B — migrate valuable local history

If local live forecasts are worth preserving:

```text
1. stop local scheduler/writes
2. create pg_dump
3. record application Git commit
4. transfer dump over SSH/SCP
5. deploy matching app schema
6. restore into production Postgres
7. verify row counts
8. verify prediction/context hashes
9. start workers/bot
```

Do not copy Docker volume internals.

---

# 10. Environment parity

Local and production should use the same major versions:

- Python;
- PostgreSQL;
- Redis;
- application dependencies.

Docker provides this parity.

Production differs mainly by:

- secrets;
- restart policies;
- resource limits;
- logging;
- backup;
- number of workers.

---

# 11. Resource limits

On a small VPS start conservatively.

Example principles:

- one Celery worker process or low concurrency;
- no local LLM inference;
- external API calls only;
- Postgres memory defaults reviewed;
- log rotation;
- no unnecessary dashboard services.

Measure:

```text
RAM
CPU
disk
container restart count
DB size
```

Hermes has priority: sports deployment must not destabilize it.

---

# 12. Rollback

Before deployment update:

- backup DB;
- record old Git commit;
- run migration preview/check;
- know whether DB migration is backward-compatible.

Rollback application independently from Hermes.

---

# 13. Secrets movement

Never ask the coding model to place server passwords/API keys into repository files.

Production secrets can be entered through:

- server `.env`;
- secret manager later.

SSH keys stay outside repo.

---

# 14. Migration acceptance criteria

- [ ] Fresh local machine can boot project.
- [ ] Mock mode works without external API keys.
- [ ] Sandbox mode can analyze one fixture.
- [ ] Local DB can be dumped/restored.
- [ ] Production can start from clean Git checkout.
- [ ] Hermes is not referenced by application runtime.
- [ ] No Docker volume copy is needed for migration.
