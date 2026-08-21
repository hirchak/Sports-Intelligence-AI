# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M2 + M2.1 + M2.2 fixes — awaiting final review  
**Review target branch:** `build/m2`  
**Review target commits:** `bdb5ef3`, `3f62348`, `6625d7c`, `7e71ed0`,
`ac4188a` (M2); `ea9b4a8`, `1de60af`, `1dcd7cd` (M2.1);
**`118aaab` (fingerprint/CAS/index sync), `dc5d2e0` (arbiter/worker init),
`e236f96` (docs/state)** (M2.2) — see Git section  
**CI status:** green on `build/m2` (unit, integration with isolated
Postgres/Redis, compose validation)  
**Previous review:** M2.1 → PASS WITH FIXES; fixes implemented in M2.2  
**Previous accepted state:** `main` = `25dda83` (M1 accepted, tag `v0.2-m1`)

---

# What changed since the last review

M2.2 fixes (all items from the PASS WITH FIXES verdict):

1. **Canonical request fingerprint** — deterministic
   `provider:endpoint_family:sorted(params)` including date AND timezone;
   stored in `provider_observations`; tests cover stability (same
   date+tz), tz-sensitivity (different tz → different fingerprint),
   parameter-order independence and provider distinction.
2. **FAILED-job requeue race** — CAS transition
   `transition_job_status_if(FAILED → PENDING)`; the HTTP layer re-reads
   the status after enqueue and can never downgrade RUNNING/SUCCEEDED;
   regression test simulates a worker status transition between
   `apply_async()` and the HTTP-side update (job remains RUNNING).
   Full outbox still M4.
3. **ORM metadata synchronized with migration 0003** — composite
   `ix_fixtures_league_kickoff` / `ix_fixtures_status_kickoff` declared in
   the ORM; stale single-column `index=True` removed (single kickoff
   index kept deliberately for date-only queries); schema drift verified
   with `alembic check` at head in integration tests/CI — no new upgrade
   operations.
4. **Hardened atomic identity race** — arbiter resolution no longer uses
   `scalar_one()` without fallback: bounded safe resolution (winner row →
   use; empty → fresh mapping SELECT; bounded retries); no orphan
   Team/Fixture; targeted synchronized-start test (6 participants on one
   team identity) proves exactly 1 mapping, exactly 1 Team, identical
   UUID for all callers.
5. **Worker initialization exception-safe** — engine/provider cleanup in
   `finally` with independent try/excepts; provider/config init failure
   marks the job FAILED when the DB is available and re-raises the
   original exception (integration + unit tests).

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
uv run pytest -q -m "not integration"        # 79 passed
make test-integration                        # 20 passed, isolated sports_intel_test
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

Live evidence: bounded API-Football smokes passed in M2/M2.1 (383
fixtures in ONE request, 1 eligible league, idempotent re-runs, no key
in logs). M2.2 changed no HTTP contract, so the live smoke was NOT
repeated (quota preserved); MOCK-mode discovery through the full stack
was re-verified (idempotent, canonical fingerprint stored in
observations).

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
