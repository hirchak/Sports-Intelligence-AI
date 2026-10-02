#!/usr/bin/env bash
set -euo pipefail
# Local only. Never overwrite the operator's env or remove existing volumes.
endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
case "${DOCKER_HOST:-$endpoint}" in unix://*) ;; *) echo 'Local Docker Unix socket required' >&2; exit 1;; esac
[[ -f .env ]] || cp .env.example .env
chmod 600 .env
uv sync --frozen --dev
# Serial build also works on Docker Desktop versions with the multi-service bake issue.
for service in sports-api sports-worker sports-beat; do docker compose build "$service"; done
docker compose up -d --wait sports-postgres sports-redis
docker compose run --rm sports-api alembic upgrade head
docker compose run --rm sports-api python scripts/seed_leagues.py
docker compose up -d --wait sports-api sports-worker sports-beat
# Health probes do not assume a host port: compatible with isolated private topology.
docker compose exec -T sports-api python -c "import urllib.request; [urllib.request.urlopen('http://127.0.0.1:8000/'+p, timeout=5) for p in ('health','ready')]; print('health/ready PASS')"
docker compose --profile telegram config -q
