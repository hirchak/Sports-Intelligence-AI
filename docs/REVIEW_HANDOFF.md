# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M2 + M2.1 fixes — awaiting final review  
**Review target branch:** `build/m2`  
**Review target commits:** `bdb5ef3` (DTOs + adapter), `3f62348` (schema +
discovery), `6625d7c` (API + Celery), `7e71ed0` (compose/docs),
`ac4188a` (CI fix), **`ea9b4a8` (timezone/provider safety), `1de60af`
(evidence history + atomic identity), `1dcd7cd` (docs/state)** — see Git
section  
**CI status:** green on `build/m2` (unit, integration with isolated
Postgres/Redis, compose validation)  
**Previous review:** M2 → PASS WITH FIXES; fixes implemented in M2.1  
**Previous accepted state:** `main` = `25dda83` (M1 accepted, tag `v0.2-m1`)

---

# What changed since the last review

M2.1 fixes (all items from the PASS WITH FIXES verdict):

1. **`retrieved_at` semantics** — captured after the final successful
   response (post-retry); regression test with retry/delay.
2. **Immutable evidence history (ADR-0009)** — deduplicated content
   (`raw_provider_payloads`) + append-only `provider_observations` (one
   row per retrieval event with its own `retrieved_at`); migration 0003
   migrates existing rows; replay resolves the snapshot available at
   `as_of` via `retrieved_at <= as_of`.
3. **Atomic provider identity** — PostgreSQL CTE arbiter for teams and
   fixtures: the unique mapping insert decides the winner and the entity
   row is created in the same statement; concurrent discoveries produce
   exactly one Team row and one mapping (gather-based test). Fixture
   refresh updates mutable metadata in place (same UUID; kickoff-change
   test). `upsert_league_id` syncs `enabled` (false→true→false test).
4. **Per-provider enabled leagues** — IDs resolved for the CURRENT
   provider only; zero enabled → empty summary with 0 external calls
   (counting transport test); `config/leagues.mock.yaml` carries explicit
   `mock:` + `api_football:` IDs.
5. **Timezone** — "today" via `APP_TIMEZONE`; `?date=` boundaries are
   local-day UTC windows (DST-aware); API-Football receives
   `timezone=APP_TIMEZONE`; DB timestamps stay UTC; midnight/DST tests.
6. **Provider safety** — `mock` only when explicitly configured; unknown
   values fail fast with `ProviderConfigError` (typo test).
7. **Job enqueue failure** — failed enqueue marks the job FAILED (502);
   repeated POST re-enqueues the SAME job row (PENDING), no duplicates.
8. **Missing data** — nullable team/league names; required identity
   (fixture status) fails validation; no invented "Unknown"/"UNKNOWN".
9. **ADR-0008 reconciled** — composite indexes `(league_id, kickoff_at)`
   and `(status, kickoff_at)` actually created in migration 0003.

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
uv run pytest -q -m "not integration"        # 74 passed
make test-integration                        # 16 passed, isolated sports_intel_test
uv run ruff check .
uv run ruff format --check .
uv run mypy src                              # 51 source files, strict
docker compose config -q
docker compose up -d --build                 # api/postgres/redis/worker/beat
curl http://127.0.0.1:8000/health            # 200
curl http://127.0.0.1:8000/ready             # 200
curl -X POST http://127.0.0.1:8000/v1/jobs/discover -d '{"date":"2026-08-21"}'
curl "http://127.0.0.1:8000/v1/fixtures?date=2026-08-21"
```

CI runs unit + integration (isolated service containers) + compose
validation on every push; all three jobs green on `build/m2`.

Live evidence (bounded): M2.1 ran one real API-Football request (383
fixtures, 1 eligible league) through the stack — job SUCCEEDED, a new
observation row appended while content stayed deduplicated, no API key
in logs. Repeat-run idempotency additionally verified in MOCK mode
(0 created / 3 updated / observation appended).

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
