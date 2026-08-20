# Current Task

**Status:** COMPLETE — awaiting review  
**Milestone:** M1 — Core Infrastructure  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-20  
**Last updated:** 2026-08-20

---

# Task

Turn the M0 skeleton into a real local core infrastructure for future
pipelines. → **Done, commits on `build/m1`.**

---

# Acceptance criteria — verified

- `pytest -m "not integration"` → 34 passed (local + CI)
- `pytest -m integration` → 3 passed against real Postgres/Redis
  (local compose + CI service containers)
- Ruff / format check / strict mypy → clean
- `docker compose config -q` (+ dev override) → OK
- Five services up locally; `/health` 200; `/ready` 200 via shared
  lifespan resources; worker "ready" with 6 queues; beat started;
  `control.ping` executed through the broker (smoke)
- `alembic upgrade head` on fresh DB creates `jobs`/`job_attempts`;
  apply→repeat→downgrade→reapply tested in CI
- MOCK mode keyless → verified

---

# Work notes

- 2026-08-20: M0 finalized in main (PR #2). ADR-0006 written.
- 2026-08-20: Implementation + verification complete (see worklog).

---

# Completion

- Status set to COMPLETE.
- Commits: see `docs/REVIEW_HANDOFF.md`.
- `docs/IMPLEMENTATION_STATUS.md`, `docs/AI_WORKLOG.md`,
  `docs/REVIEW_HANDOFF.md` updated.
- Stopped before M2, as required.
