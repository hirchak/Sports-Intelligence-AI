# Telegram

Status: **planned** — no bot code exists in M0 (M3).
Authoritative design: `07_TELEGRAM_BOT_SPEC.md`.

## Role

The bot is a private, thin control plane. It calls application services and
renders results. No forecasting/business logic in handlers.

## Hard requirements (already reflected in M0 config)

- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_IDS` environment variables
  (declared in `Settings` and `.env.example`);
- allowlist enforcement, unknown users rejected without detail leakage;
- long polling in v1 (no public webhook endpoint);
- internal stack traces never reach Telegram.

## Planned commands

`/start /dashboard /today /fixtures /predictions /match /analyze /refresh
/stats /evaluate /improvements /health /settings /help`
plus admin-only `/discover /evaluate /retry`.

## Implementation notes for M3

- `aiogram` 3 dependency will be added in M3.
- Every manual action gets an idempotency key; repeated taps must not
  duplicate work.
- Publisher sends only after prediction persistence succeeds.
- Telegram must never display "guaranteed/safe bet" language.
