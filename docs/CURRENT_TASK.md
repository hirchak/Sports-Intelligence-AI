# Current Task

**Status:** COMPLETE — awaiting independent review  
**Milestone:** M3.1 (minimal fix after final M3 review: PASS WITH TWO SMALL FIXES)  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-21  
**Last updated:** 2026-08-21

---

# Task

Apply the two required small fixes on `build/m3`. → **Done, commit on `build/m3`.**

---

# Acceptance criteria — verified

- every callback query (valid and malformed `fx:` / `pg:` / `rf:` / `menu:*`
  payloads, catch-all) is acknowledged exactly once so the Telegram
  client stops its loading indicator → OK
- malformed callbacks (`fx:not-a-uuid`, `pg:not-a-date:99`,
  `rf:not-a-date`) get a safe UI response, never call the backend, and
  never crash → OK
- missing `TELEGRAM_BOT_TOKEN` at startup raises `SystemExit(1)` and
  the process exits with a non-zero status (not silently swallowed) → OK
- normal Ctrl+C (`KeyboardInterrupt`) is still handled cleanly for normal
  manual shutdown → OK
- token is never logged, today or in any future path → OK
- scope guard: scheduler / automatic discovery / odds / lineups /
  injuries / quota manager / research / MatchContext / LLM prediction /
  live analysis — still NOT implemented → OK
- 159 unit + 26 integration green; Ruff; format; strict mypy (62 source
  files); alembic check (in integration); compose validation →
  OK
- one coherent M3.1 commit, no merge of `build/m3` into `main`,
  M4 not started → OK

---

# Work notes

- see `docs/AI_WORKLOG.md` for the M3.1 entry.

---

# Completion

- Status set to COMPLETE.
- Commit: see `docs/REVIEW_HANDOFF.md`.
- State files/docs updated. No merge to main; stopped before M4.
