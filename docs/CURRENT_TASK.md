# Current Task

**Status:** COMPLETE — awaiting review  
**Milestone:** M2 — Sports Provider + Fixture Discovery  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-20  
**Last updated:** 2026-08-20

---

# Task

First real sports provider (API-Football) + deterministic fixture
discovery. → **Done, commits on `build/m2`.**

---

# Acceptance criteria — verified

- Typed DTOs (no `dict[str, Any]` on discovery path) → OK
- API-Football adapter: env-only key, timeout, bounded retry, normalized
  errors, safe logging, injected transport → OK (unit-tested)
- Batch-first discovery, no N+1 (guard test) → OK
- Raw evidence persistence with hash dedup → OK
- Migration 0002 on fresh test DB (apply/repeat/downgrade/reapply) → OK
- Discovery idempotency (repeat → no duplicates) → OK (integration + live)
- League YAML config + seed path → OK
- `GET /v1/fixtures` (+filters), `GET /v1/fixtures/{id}`,
  `POST /v1/jobs/discover` (idempotent job) → OK
- Celery `sports.discover_fixtures` on `sports_io`; no schedule → OK
- Mock mode keyless; contract tests incl. malformed/errors/timeout/key-leak
  → OK
- Live smoke (bounded, 2 calls) with real key → OK; key only in `.env`
- Unit 63 / integration 10 / ruff / format / strict mypy / compose /
  docker smoke → OK

---

# Work notes

- 2026-08-20: M1 finalized (PR #3, tag `v0.2-m1`); M2 implemented and
  verified, including a bounded live API-Football smoke.

---

# Completion

- Status set to COMPLETE.
- Commits: see `docs/REVIEW_HANDOFF.md`.
- State files and docs updated. Stopped before M3; no merge to main.
