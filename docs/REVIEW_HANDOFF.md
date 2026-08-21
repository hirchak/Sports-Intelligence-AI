# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M3.1 — Telegram base UI / private control plane — minimal
fix (final M3 review: PASS WITH TWO SMALL FIXES); awaiting independent
review  
**Review target branch:** `build/m3`  
**Review target commits:** `3ad5dc0` (M3: Russian Telegram bot UI with
button-based menus and Back navigation) — see Git section  
**CI status:** green on `build/m3` (unit, integration with isolated
Postgres/Redis, compose validation incl. telegram profile)  
**Previous review:** M3 → **PASS WITH TWO SMALL FIXES**; fixes implemented
in M3.1  
**Previous accepted state:** `main` = `c737f80` (M2 accepted, tag
`v0.3-m2`)

---

# What changed since the last review

M3.1 (the two required small fixes from the final M3 review):

- **Telegram callback acknowledgement is guaranteed exactly once.** The
  shared `_answer_from_callback` helper calls `answer_callback`
  before editing/sending; every callback handler delegates through it
  on its response path; the explicit `answer_callback` calls that
  previously preceded it were removed. As a result, malformed `fx:` /
  `pg:` / `rf:` payloads still get a safe UI response (`Неизвестное
  действие.` + Back button) AND the Telegram client stops its
  loading indicator. Regression tests for `fx:not-a-uuid`,
  `pg:not-a-date:99`, `rf:not-a-date` assert `answer_callback` was
  called, the user received a safe response, and no backend call was
  made.
- **Startup failure is non-zero.** `bot.__main__.main()` now suppresses
  `KeyboardInterrupt` only; `SystemExit` (e.g. raised when
  `TELEGRAM_BOT_TOKEN` is empty) propagates so the process exits with
  the failure code. Normal Ctrl+C remains a clean shutdown. The
  startup refusal message is a static string — token is never logged.
- **Scope guard** — explicitly out of M3 / M3.1 and not touched:
  scheduler, automatic discovery, sports collectors, odds, lineups /
  injuries, quota manager, research, MatchContext, LLM prediction,
  live football analysis. The Telegram bot remains a thin UI over the
  FastAPI backend.
- **Future roadmap** (documented only, NOT implemented): the scheduled
  pipeline (M4+) must populate PostgreSQL automatically, independent of
  Telegram usage; Telegram fixture screens must read essentially-ready
  data from the DB; a future availability / lineup collector may do
  bounded pre-kickoff refresh; a future confirmed / new lineup snapshot
  may create a new `PREMATCH_FINAL` prediction rather than overwriting
  `MORNING`; future live analytics is a separate post-v1 extension, not
  part of M3 / M4.

M3 (final independent review requested):

- **Telegram bot as a thin UI** over the existing FastAPI control plane.
  The handler layer (`sports_intelligence.bot`) never touches provider
  adapters, DB or LLM; all backend traffic goes through a typed
  `BackendClient` (health/ready, fixtures list, fixture detail, discover
  enqueue) whose errors are normalized into bot-safe text (no URLs,
  bodies, stack traces or secrets ever reach Telegram).
- **Central allowlist middleware** registered for both messages and
  callback queries using `TELEGRAM_BOT_TOKEN` +
  `TELEGRAM_ALLOWED_USER_IDS`. Unknown users receive "Доступ запрещён."
  (or a silent callback answer). Empty allowlist denies everyone;
  handlers never duplicate the check.
- **Russian UI, single language** — all Telegram-facing text lives in
  `bot/strings.py`; commands and callbacks render the same Russian
  strings.
- **Button-based navigation** — main menu (Сегодня / Найти / Здоровье
  / Помощь); every screen has a «← Назад» button returning to the main
  menu; find menu offers yesterday / today / tomorrow as quick picks
  plus the `/fixtures ГГГГ-ММ-ДД` hint for arbitrary dates. Commands
  remain as a power-user fallback (`/start /help /dashboard /today
  /fixtures [date] /match <uuid> /health /discover [date]`) and reach
  the same screens. `/predictions /stats /evaluate /improvements`
  return a clear "недоступна в этой вехе (M3)" message — no fake
  screens, no invented metrics.
- **Inline callbacks** — short stable payloads (`fx:<uuid>`,
  `pg:<date>:<page>`, `rf:<date>`, `disc`, `health`, `menu:*`); under
  Telegram's 64-byte limit; no secrets, no JSON. Fixture view,
  pagination, refresh, discover, health, main menu, find menu.
  Malformed/tampered payloads are answered harmlessly; repeated taps
  rely on backend idempotency (no second idempotency scheme inside
  Telegram).
- **Rendering** — /today grouped by league ordered by kickoff; kickoff
  shown in `APP_TIMEZONE` (DB stays UTC); Russian month abbreviations
  (янв., фев., …, авг., …); missing team names rendered as "—"
  (stored data never mutated); pagination (8 per page, Prev/Next +
  Refresh); HTML escaping for all backend-provided strings.
- **Transport separated from handlers** — `TelegramTransport` protocol
  (send_text / edit_text / answer_callback) with an aiogram
  implementation and an in-memory fake; 72 deterministic bot unit
  tests require no token and no network.
- **Docker Compose `telegram` profile** — isolated `sports-telegram`
  service (no exposed ports), internal networking to `sports-api`,
  bot env via `BOT_BACKEND_BASE_URL`; the ordinary
  api/postgres/redis/worker/beat stack starts without any Telegram
  credentials.
- **Live Telegram smoke** with a real token + allowlisted user:
  English commands /start /today /health /discover + inline fixture
  tap verified through bot/worker logs; Russian main-menu + button
  navigation verified live by user screenshot. MOCK-mode discovery
  round-trip verified idempotent (0 created / 3 updated; duplicate
  POST → `already_queued: true`). Note: one accidental live
  API-Football call was consumed before the smoke was pinned to MOCK
  (documented in the worklog; quota-safe default restored afterwards).

---

# What should the reviewer verify?

- every callback query (valid and malformed `fx:` / `pg:` / `rf:` /
  `menu:*` payloads, catch-all) is acknowledged exactly once so the
  Telegram client stops its loading indicator;
- malformed callbacks (`fx:not-a-uuid`, `pg:not-a-date:99`,
  `rf:not-a-date`) get a safe UI response, never call the backend,
  and never crash;
- missing `TELEGRAM_BOT_TOKEN` at startup raises `SystemExit(1)` and
  the process exits with a non-zero status;
- normal Ctrl+C (`KeyboardInterrupt`) is still handled cleanly;
- token is never logged;
- scope guard: scheduler, automatic discovery, sports collectors,
  odds, lineups / injuries, quota manager, research, MatchContext,
  LLM prediction, live football analysis — still NOT implemented;
- M3 review items remain true (Russian UI, button-based navigation,
  Back button, central allowlist, typed backend client, no provider
  calls inside the bot, idempotent /discover, mute UI on backend
  errors, long polling only, secrets never logged, compose
  `telegram` profile isolated, unit tests do not require a token).

---

# Commands claimed as passing

```bash
uv sync --frozen --dev
uv run pytest -q -m "not integration"        # 159 passed
make test-integration                        # 26 passed, isolated sports_intel_test
uv run ruff check .
uv run ruff format --check .
uv run mypy src                              # 62 source files, strict
docker compose config -q
docker compose --profile telegram config -q
docker compose build sports-telegram
docker compose --profile telegram up -d sports-telegram
```

CI runs unit + integration (isolated service containers) + compose
validation on every push; all three jobs green on `build/m3`.

Live evidence: bounded Telegram smoke with real token + allowlisted
user — Russian main menu + button navigation verified live; English
commands path verified; MOCK-mode discovery round-trip verified
idempotent end-to-end. One accidental live API-Football call was
consumed before the smoke was pinned to MOCK; documented in the
worklog and disposable. M3 changed the bot UI only (transport,
payload, language) — no provider HTTP contract change, so the live
sports data path was not re-exercised against an external service.

Reviewer must not assume tests passed based on status text alone.

---

# Known limitations

- Live verification of the sports-provider HTTP path is a single-date,
  single-league bounded smoke from M2/M2.1 — not multi-day production
  usage. M3 did not re-exercise it.
- One accidental live API-Football call was consumed during the M3
  smoke (1301 fixtures received, 5 created, key never logged); the
  smoke was then pinned to MOCK and the stack was restored to the
  quota-safe default (`config/leagues.yaml`, all leagues disabled).
- `job_attempts` rows are not written yet (M4 debt); only `jobs.status`
  is updated.
- QuotaManager / request ledger deferred to M4 (adapter captures
  rate-limit headers already).
- Odds / search / LLM protocols still typed as `dict[str, Any]`
  placeholders until their milestones.
- Docker Desktop multi-service bake build bug (per-service build
  workaround documented in `docs/LOCAL_DEVELOPMENT.md`).
- Slack-style react-on-tap / threaded updates are not implemented;
  status messages are static until the next user interaction or
  /discover completion.

---

# Files of highest relevance

- `src/sports_intelligence/bot/app.py` — aiogram Bot/Dispatcher factory
- `src/sports_intelligence/bot/access.py` — central allowlist middleware
- `src/sports_intelligence/bot/backend_client.py` — typed backend client
- `src/sports_intelligence/bot/transport.py` — transport protocol
- `src/sports_intelligence/bot/context.py` — AppContext
- `src/sports_intelligence/bot/strings.py` — Russian UI text constants
- `src/sports_intelligence/bot/formatting.py` — renderers + keyboards
- `src/sports_intelligence/bot/menu.py` — main menu / find / dashboard
  keyboards
- `src/sports_intelligence/bot/handlers.py` — commands + callbacks
- `src/sports_intelligence/bot/callback_data.py` — payload schemas
- `src/sports_intelligence/bot/__main__.py` — long-polling entrypoint
- `tests/telegram_fakes.py` — FakeTransport
- `tests/unit/test_bot_*.py` — 72 deterministic bot unit tests
- `compose.yaml` — `telegram` profile
- `docs/TELEGRAM.md`, `docs/IMPLEMENTATION_STATUS.md`,
  `docs/REVIEW_HANDOFF.md`
- Git diff `v0.3-m2..build/m3`

---

# Questions for reviewer

1. Is the central allowlist middleware (message + callback) sufficient,
   or are there paths where it could be bypassed (e.g., update types
   outside its registration)?
2. Is the typed `BackendClient`'s error normalization sufficient, or
   should message-level errors also go through the same renderer?
3. Is the Russian UI consistent and unambiguous, or are there screens
   where the labels would confuse a primary Russian-speaking user?
4. Is the button-based navigation sufficient, or should the fixture
   detail screen also offer a "Back to date" jump?
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
