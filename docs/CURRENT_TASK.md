# Current Task

**Status:** COMPLETE — awaiting independent review  
**Milestone:** M3 — Telegram base UI / private control plane  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-21  
**Last updated:** 2026-08-21

---

# Task

Implement the first real private Telegram control UI over the existing
backend on branch `build/m3`. Telegram is a thin UI: aiogram handlers →
typed backend client → existing FastAPI endpoints. No provider calls, no
LLM, no prediction logic inside handlers. → **Done, commits on `build/m3`.**

UI is in Russian (single language). Navigation is button-based from the
main menu; every screen has a «← Назад» button returning to the main
menu. Commands remain as a power-user fallback.

---

# Acceptance criteria — verified

- aiogram 3 bot factory, long polling, structured JSON logging, clean
  shutdown; no webhook → OK
- central allowlist middleware (message + callback), unknown users get
  minimal denial / silent answer; no secrets/details → OK
- typed backend client (health/ready, fixtures list, fixture detail,
  discover) with bot-safe error normalization; handlers never touch raw
  response dicts → OK
- commands /start /help /dashboard /today /fixtures /match /health
  /discover; /predictions /stats /evaluate /improvements return a clear
  "not available in this milestone" message → OK
- **Russian UI** (single language) covering welcome, help, dashboard,
  fixture list, fixture detail, health, discover, find, error and
  access-denied paths → OK
- **Button-based navigation**: main menu with Сегодня / Найти /
  Здоровье / Помощь buttons; every screen has a «← Назад» button
  returning to the main menu; find menu offers yesterday / today /
  tomorrow quick picks → OK
- inline callbacks: fixture view, pagination (Prev/Next), refresh,
  discover, health, menu callbacks; payloads short/secret-free;
  repeated/malformed taps harmless → OK
- /today grouped by league/kickoff, kickoff in APP_TIMEZONE, missing
  team names rendered safely ("—"), Russian month abbreviations
  (авг., янв., …), pagination → OK
- /discover delegates to backend POST /v1/jobs/discover; duplicate taps
  keep backend idempotency (no second scheme in Telegram) → OK
- /health concise: API / Database / Redis → OK
- Docker Compose `telegram` profile, internal networking, no exposed
  ports; ordinary dev stack starts without a token → OK
- unit tests require no token (transport separated from handlers) → OK
- 151 unit + 26 integration green; Ruff; format; strict mypy (62 source
  files); alembic check (in integration); compose validation; secret
  scan → OK
- live Telegram smoke with real token + allowlisted user: /start
  /today /health /discover + inline fixture tap (English commands)
  verified; Russian main menu + button navigation verified live
  (screenshot) → OK (see worklog for the one accidental live API
  call)
- no merge of `build/m3` into `main`; stopped after M3; M4 not started
  → OK

---

# Work notes

- 2026-08-21: M2 merged to main (PR #4), tag `v0.3-m2`, `build/m3`
  created from main; M3 implemented (initial English commands), then
  pivoted to Russian button-based navigation per user feedback; full
  suite green; live smoke verified (see worklog).

---

# Completion

- Status set to COMPLETE.
- Commits: see `docs/REVIEW_HANDOFF.md`.
- State files/docs updated. No merge to main; stopped before M4.
