# Telegram

Status: **M0–M10 independently accepted** — private thin control plane with prediction, results,
stats, experiments and improvement screens. M10 verifies local test transport and operational safety.
Authoritative design: `07_TELEGRAM_BOT_SPEC.md`.

## Role

The bot is a private, thin control plane. It calls the FastAPI backend
through a typed `BackendClient` and renders results. No
forecasting/business logic in handlers; no provider, DB or LLM access.

## UI language

Single language: Russian. All user-facing text lives in
`bot/strings.py`; the codebase and docs stay in English.

## Navigation

Button-based: every screen has a «← Назад» button returning to the
main menu. Main menu — Сегодня / Найти / Здоровье / Помощь. Find menu
offers yesterday / today / tomorrow as quick picks plus the
`/fixtures ГГГГ-ММ-ДД` hint for arbitrary dates. Commands remain as a
power-user fallback and reach the same screens.

## Implementation (M3)

- `sports_intelligence.bot` package: `app` (aiogram Bot/Dispatcher
  factory), `access` (central allowlist middleware with Russian denial),
  `backend_client` (typed methods: health/ready, fixtures list, fixture
  detail, discover; bot-safe error normalization), `transport` (send_text
  / edit_text / answer_callback protocol + aiogram implementation),
  `formatting` (Russian league grouping, APP_TIMEZONE kickoffs with
  Russian month abbreviations, HTML escaping, pagination, "—" for
  missing team names, Back button), `strings` (all Russian UI text
  constants), `menu` (main menu, find menu, dashboard keyboard, Back
  keyboard builders), `handlers` (commands + inline callbacks + menu
  callbacks), `callback_data` (short stable payloads: `fx:<uuid>`,
  `pg:<date>:<page>`, `rf:<date>`, `disc`, `health`, `menu:*`).
- Commands: `/start /help /dashboard /today /fixtures [YYYY-MM-DD]
  /match <uuid> /health /discover [YYYY-MM-DD]`. M7 adds `/predictions` and
  `/analyze <uuid>`; `/stats /evaluate /results /experiments /improvements` are implemented.
- Access control: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_IDS`,
  enforced centrally by middleware for messages and callbacks; unknown
  users receive "Доступ запрещён." (or a silent callback answer). Empty
  allowlist denies everyone.
- Long polling (no webhook), structured JSON logging, clean shutdown.
- Docker Compose `telegram` profile (`sports-telegram`), internal
  networking to `sports-api`, no exposed ports.
- Tests: 72 deterministic bot unit tests (access, formatting, backend
  client, handlers, callbacks, menu navigation) — no token required.
  Live smoke with a real token verified the initial English commands
  and the Russian main menu + button navigation.

## Hard requirements (kept)

- allowlist enforcement, unknown users rejected without detail leakage;
- internal stack traces never reach Telegram (bot-safe error texts);
- every manual action keeps backend idempotency (no second scheme in
  Telegram); repeated taps are harmless;
- Telegram never displays "guaranteed/safe bet" language.

## M7 prediction UI

Main-menu «Прогнозы» and fixture «Прогноз / Запросить анализ» buttons read or enqueue
through the typed BackendClient. Prediction screens: candidates, full probability table,
why/evidence, risks, runtime model metadata and explicit rerun. Russian UI, HTML escaping,
allowlist middleware on the M7 router, callbacks under 64 bytes and exactly one acknowledgement.

Default lists show PRIMARY only. CHALLENGER is labelled shadow and never shown as primary picks.
A rerun button derives a stable UUID from its originating run: duplicate taps reuse the new run;
its new screen can request the next rerun. The original MatchContext/phase/role/variant are pinned.
ABSTAINED/FAILED/QUEUED are separate screens; valid forecasts without passing candidates show
`NO HIGH-CONFIDENCE OPPORTUNITY`. No provider/DB calls from handlers; no automatic Telegram
push was activated. M7 was verified with test transport, not a new live Telegram smoke.

## M8 implementation

See [EVALUATION.md](EVALUATION.md) and [ADR 0011](adr/0011-m8-result-authority-and-measurement.md).
Migration 0013 adds versioned results, probability/candidate settlements, immutable evaluation runs,
normalized metrics and calibration buckets. Local scheduled date batches feed API and thin Telegram stats.


## M10 acceptance and startup

Empty allowlist refuses process startup before any network call; positive user IDs required. Existing
central middleware still denies unauthorized/missing users on messages/callbacks across every router.
Complete keyless transport gates cover today/details/analyze/duplicates/predictions/evidence/risks/model,
results/stats/experiments/improvements/health/pagination/malformed backend and safe failures. Russian
UI/navigation retained. Actual live transport smoke, bot command flow and human receipt are separate
claims in M10_ACCEPTANCE_REPORT. Do not run two polling instances on one token. No bot/core-state
dependency or automatic production promotion exists.
