# Current Task

**Status:** COMPLETE — awaiting final review  
**Milestone:** M2.1 (fix-milestone after M2 review: PASS WITH FIXES)  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-20  
**Last updated:** 2026-08-20

---

# Task

Apply M2 review fixes on `build/m2`. → **Done, commits on `build/m2`.**

---

# Acceptance criteria — verified

- retrieved_at after final response (retry test) → OK
- evidence content/observation split, ADR-0009, replay `as_of` queryable → OK
- atomic identity (CTE arbiter): concurrency test — one Team, one mapping → OK
- fixture refresh keeps UUID, updates kickoff/status/venue/round/refs → OK
- league `enabled` sync false→true→false → OK
- per-provider enabled IDs; no-op without enabled leagues (0 calls) → OK
- timezone: local today, window boundaries, DST test, adapter `timezone`
  param, API date filter in APP_TIMEZONE → OK
- provider typo → ProviderConfigError → OK
- enqueue failure → FAILED + 502; re-POST requeues same job → OK
- no invented Unknown/UNKNOWN; nullable names; required status fails → OK
- ADR-0008 ↔ migration 0003 reconciled (composite indexes created) → OK
- 74 unit + 16 integration green; ruff/format/mypy/compose green;
  MOCK + bounded live smoke green; secret scan clean → OK

---

# Work notes

- 2026-08-20: fixes implemented and verified (see worklog).

---

# Completion

- Status set to COMPLETE.
- Commits: see `docs/REVIEW_HANDOFF.md`.
- State files/docs updated. No merge to main; stopped before M3.
