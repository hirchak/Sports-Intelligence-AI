# Hetzner Deployment Runbook
## Sports Intelligence AI beside existing Hermes

Use this only after local acceptance criteria and independent audit pass.

Target:
- Ubuntu server on Hetzner
- Hermes already exists and must remain untouched
- new project deployed independently using Docker Compose

---

# Safety rule

The deployment agent is not authorized to:

- stop Hermes;
- restart Hermes;
- edit Hermes files;
- edit Hermes `.env`;
- reuse Hermes DB;
- reuse Hermes volumes;
- prune Docker globally;
- run `docker system prune`;
- delete unrelated images/containers;
- change firewall rules unless explicitly approved.

If a conflict is detected, stop the sports deployment and report it.

---

# Phase 1 — inspect server

Before copying or launching anything, collect:

```bash
uname -a
lsb_release -a || cat /etc/os-release
free -h
df -h
docker version
docker compose version
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
docker network ls
docker volume ls
ss -tulpn
```

Record:

- available RAM;
- available disk;
- existing public ports;
- existing Docker container names;
- existing networks;
- existing volumes.

Do not print secrets.

Create `docs/PRODUCTION_PREFLIGHT.md` locally with the findings, excluding sensitive values.

---

# Phase 2 — create isolated directory

Example:

```text
/opt/sports-intelligence/
```

Suggested ownership:
- dedicated deployment user where practical.

Inside:

```text
compose.yaml
.env
config/
backups/
```

Code may be deployed via Git clone/pull using a private GitHub repository.

---

# Phase 3 — production configuration

Use a production `.env` that is never committed.

Required secrets:

- Postgres password
- Telegram bot token
- Telegram allowed user IDs
- sports API key
- odds/search API keys if enabled
- runtime LLM key

Set:

```text
APP_ENV=production
APP_TIMEZONE=Europe/Warsaw
```

Telegram should use long polling initially.

No public bot webhook is required.

---

# Phase 4 — Docker isolation

Use:

```bash
docker compose -p sports-intel ...
```

Expected project services:

```text
sports-api
sports-worker
sports-beat
sports-bot
sports-postgres
sports-redis
```

Use unique volumes such as:

```text
sports_pgdata
sports_redisdata
```

Use a private project network.

Do not map PostgreSQL 5432 or Redis 6379 to the public host.

If API access is not externally needed, do not expose the API publicly.

---

# Phase 5 — deploy

Recommended sequence:

```bash
docker compose -p sports-intel config
docker compose -p sports-intel build
docker compose -p sports-intel up -d postgres redis
docker compose -p sports-intel run --rm api <migration command>
docker compose -p sports-intel up -d api worker beat bot
docker compose -p sports-intel ps
```

Use the repository's real migration/start commands, not placeholders.

---

# Phase 6 — verify

Check:

- all sports containers healthy;
- Hermes containers unchanged;
- DB migrations applied;
- Redis reachable internally;
- bot can receive `/health`;
- `/today` works;
- one controlled analysis works;
- logs contain no secrets;
- restart policy works.

Commands may include:

```bash
docker compose -p sports-intel ps
docker compose -p sports-intel logs --tail=200 api
docker compose -p sports-intel logs --tail=200 worker
docker compose -p sports-intel logs --tail=200 bot
docker stats --no-stream
```

Then compare Hermes container status with the preflight snapshot.

---

# Resource guardrail

Do not assume the current Hetzner plan is large enough.

If the server is resource constrained:

1. do not kill Hermes;
2. do not remove limits/safety controls;
3. report measured RAM/CPU/disk pressure;
4. recommend upgrading the VPS or moving sports services to another host.

Typical idle services are lightweight, but worker concurrency and database memory must be configured according to the actual machine.

Start worker concurrency low.

---

# Backup

Create a nightly PostgreSQL backup job.

Requirements:

- compressed `pg_dump`;
- 7-day local rotation initially;
- restore command documented;
- backup directory not inside a disposable container filesystem.

Test one restore into a temporary database before declaring backup complete.

Do not delete backups from unrelated projects.

---

# Updating production

Recommended:

```text
git fetch
git checkout <approved commit>
docker compose -p sports-intel build
docker compose -p sports-intel run --rm api <migration command>
docker compose -p sports-intel up -d
```

Before a schema-affecting update:

- take DB backup;
- record current Git commit;
- ensure migration downgrade/rollback strategy is known.

---

# Rollback

Rollback must be documented before the first production update.

At minimum:

1. identify previous known-good Git commit;
2. restore compatible containers;
3. if required, restore DB backup;
4. verify bot/API;
5. never rollback Hermes as part of sports rollback.

---

# Deployment completion checklist

- [ ] local E2E passed
- [ ] independent audit passed
- [ ] no secrets in Git
- [ ] server preflight documented
- [ ] Hermes unchanged
- [ ] unique Compose project
- [ ] DB/Redis private
- [ ] migrations applied
- [ ] bot restricted to allowed IDs
- [ ] `/health` works
- [ ] `/today` works
- [ ] prediction works
- [ ] worker scheduler works
- [ ] backups configured
- [ ] restore procedure documented
- [ ] rollback procedure documented
