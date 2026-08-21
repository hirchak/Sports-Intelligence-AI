# Telegram

Status: **implemented (M3)** — private thin control plane on `build/m3`.
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
  /match <uuid> /health /discover [YYYY-MM-DD]`. `/predictions /stats
  /evaluate /improvements` return a clear "недоступна в этой вехе
  (M3)" message.
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
