# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M2 — Sports Provider + Fixture Discovery, awaiting review  
**Review target branch:** `build/m2`  
**Review target commits:** `bdb5ef3` (DTOs + adapter), `3f62348` (schema +
discovery service), `6625d7c` (API + Celery task), `7e71ed0` (compose/docs),
`ac4188a` (CI test fix) — see Git section  
**CI status:** green on `build/m2` (unit, integration with isolated
Postgres/Redis, compose validation)  
**Previous accepted state:** `main` = `25dda83` (M1 accepted, tag `v0.2-m1`)

---

# What changed

1. **Typed provider DTOs** (`providers/dto.py`) — `ProviderLeague`,
   `ProviderSeason`, `ProviderTeam`, `ProviderFixture`,
   `FixtureDiscoveryResult`, `ProviderResponseMetadata`. UTC-normalized
   kickoff, explicit `None` for missing fields. M1 tech debt closed for
   the discovery path.
2. **API-Football adapter** (`providers/sports/api_football.py`) — async
   httpx, env-only API key, configurable base URL, bounded retry
   (timeout/transport/429/5xx retryable; 401/403 non-retryable),
   normalized `ProviderError` hierarchy, rate-limit metadata, raw payload
   returned for evidence, injectable transport, one shared client per
   instance. Choice rationale: ADR-0007.
3. **Mock provider** (`providers/sports/mock.py`) — recorded, sanitized
   API-Football-shaped responses; keyless; used by MOCK mode/CI/tests.
4. **Migration 0002** — `leagues`, `seasons`, `teams`, `fixtures`,
   `provider_entity_ids`, `raw_provider_payloads`; UUID PKs, UTC, unique
   constraints and indexes; PostgreSQL upserts. Scope: ADR-0008.
   No odds/prediction/research tables.
5. **FixtureDiscoveryService** — batch-first (one date-level request),
   enabled leagues filtered locally, raw payload hash-deduplicated,
   idempotent entity upserts with provider identity on mappings.
6. **League config** — YAML (`config/leagues.yaml`, all leagues disabled
   by default; `config/leagues.mock.yaml` demo), `make seed` path.
7. **API** — `GET /v1/fixtures` (date/league filters), `GET
   /v1/fixtures/{id}` (404), `POST /v1/jobs/discover` (jobs row +
   idempotency key `discover:{provider}:{date}` + Celery enqueue; no
   long-running provider call in the handler).
8. **Celery** — `sports.discover_fixtures` on `sports_io`; job status
   RUNNING/SUCCEEDED/FAILED; no automatic schedule (no quota spend unless
   explicitly POSTed).

---

# What should the reviewer verify?

- provider JSON never leaks into domain/API schemas (DTO boundary);
- adapter retry classification and key handling (no key in logs/errors);
- discovery is fully idempotent (rows, mappings, raw payload dedup);
- N+1 guard test is meaningful (single request for N fixtures);
- migration 0002 applies/downgrades/reapplies on a fresh DB;
- no scope creep (no odds/research/MatchContext/prediction/Telegram);
- test-DB isolation guard still intact (dev DB protected);
- compose isolation unchanged (loopback ports, named volumes).

---

# Commands claimed as passing

```bash
uv sync --frozen --dev
uv run pytest -q -m "not integration"        # 63 passed
make test-integration                        # 10 passed, isolated sports_intel_test
uv run ruff check .
uv run ruff format --check .
uv run mypy src                              # 50 source files, strict
docker compose config -q
docker compose up -d --build                 # api/postgres/redis/worker/beat
curl http://127.0.0.1:8000/health            # 200
curl http://127.0.0.1:8000/ready             # 200
curl -X POST http://127.0.0.1:8000/v1/jobs/discover -d '{"date":"2026-08-21"}'
curl "http://127.0.0.1:8000/v1/fixtures?date=2026-08-21"
```

CI runs unit + integration (isolated service containers) + compose
validation on every push; all three jobs green on `build/m2`.

Live evidence (bounded, 2 API calls): real API-Football discovery of
2026-08-21 fetched 383 fixtures in ONE request, persisted 1 eligible
Premier League fixture (Arsenal vs Coventry), raw payload stored
(hash-deduplicated), repeat run idempotent (0 created / 1 updated /
payload dedup), job SUCCEEDED, rate-limit headers observed, key absent
from logs.

Reviewer must not assume tests passed based on status text alone.

---

# Known limitations

- Live verification is a single-date, single-league bounded smoke — not
  multi-day production usage.
- `job_attempts` rows are not written yet (M4 debt); only `jobs.status`
  is updated.
- QuotaManager/request ledger deferred to M4 (adapter captures
  rate-limit headers already).
- Odds/search/LLM protocols still typed as `dict[str, Any]` placeholders
  until their milestones.
- Docker Desktop multi-service bake bug (per-service build workaround
  documented).

---

# Files of highest relevance

- `src/sports_intelligence/providers/dto.py`
- `src/sports_intelligence/providers/sports/api_football.py`
- `src/sports_intelligence/providers/sports/mock.py`
- `src/sports_intelligence/pipelines/discover_fixtures.py`
- `src/sports_intelligence/db/repositories/discovery.py`
- `src/sports_intelligence/db/migrations/versions/0002_*.py`
- `src/sports_intelligence/api/routes/{fixtures,jobs}.py`
- `src/sports_intelligence/workers/tasks/sports.py`
- `docs/adr/0007-api-football-first-provider.md`
- `docs/adr/0008-m2-schema-scope-and-upserts.md`
- `config/leagues.yaml`, `config/leagues.mock.yaml`
- `tests/unit/test_api_football_adapter.py`
- `tests/integration/test_fixture_discovery.py`
- Git diff `main..build/m2`

---

# Questions for reviewer

1. Are the DTO boundary and adapter design sufficient to swap providers
   later (Sportmonks)?
2. Is discovery idempotency watertight under concurrent jobs (upsert
   races)?
3. Does raw evidence persistence satisfy provenance requirements
   (spec 14) for future MatchContext references?
4. Are there quota pitfalls in the batch-first flow?
5. Is the next milestone safe to start?

---

# Reviewer output expected

```text
VERDICT: PASS / PASS WITH FIXES / FAIL

P0 critical
P1 high
P2 medium
P3 low

Tests independently run:
...

Required fixes before next milestone:
...

Safe to begin next milestone:
YES / NO
```
