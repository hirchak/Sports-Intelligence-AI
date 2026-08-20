# ADR-0004: Runtime modes and startup validation policy

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M0

## Context

`13_LOCAL_DEV_TO_HETZNER_MIGRATION.md` defines three local modes (MOCK,
SANDBOX, LIVE_LOCAL). Master spec §7 requires strong configuration validation
at startup. MOCK must work without any external API keys.

## Decision

- `APP_ENV` accepts `mock | sandbox | live_local` (case-insensitive; normalized
  to lowercase internally).
- In `mock` mode no external keys are required; the application runs fully
  offline.
- In `sandbox`/`live_local` modes, every configured provider that has a
  provider name set must have its corresponding API key set; otherwise startup
  fails with a clear validation error.
- `TELEGRAM_ALLOWED_USER_IDS` uses a comma-separated format, parsed by an
  explicit `field_validator(mode="before")`; the field is annotated with
  pydantic-settings `NoDecode` so the env source never attempts JSON decoding
  of comma-separated values.
- Empty environment variables are ignored (`env_ignore_empty=True`): an empty
  `TELEGRAM_ALLOWED_USER_IDS=` yields the default `[]`, and empty optional
  keys behave as unset.
- `extra="ignore"` (was `forbid` in M0): the shared `.env` legitimately
  contains Compose-only variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `POSTGRES_DB`) that are not `Settings` fields and must not break startup.
  Type/format validation of all declared application settings is still
  enforced and covered by tests (e.g. non-numeric `DEFAULT_MIN_ODDS` fails).
- Telegram bot token is NOT validated by `Settings` in M0: the bot is a
  separate process (M3) and will validate its own requirements. This is a
  deliberate relaxation to keep the API usable in sandbox without a bot token.

## Alternatives

- Validating the Telegram token at Settings level now — rejected: the API and
  bot are separate processes; coupling them at config level would block
  sandbox API-only work.
- `extra="forbid"` with `POSTGRES_*` added as `Settings` fields — rejected:
  couples application config to Compose plumbing.
- Filtering sources so Compose-only keys never reach pydantic — possible but
  adds custom source code for no functional gain over `extra="ignore"`.

## Consequences

- `docker compose up` works out of the box with `.env.example` (mock mode).
- Misconfiguration of declared settings fails fast with actionable messages.
- Unknown-but-declared-field typos are no longer rejected; mitigated by the
  dotenv regression tests covering every documented variable.

## Rollback/Migration

Adding stricter mode requirements later (e.g. require bot token in
`live_local`) is a config-only change. Re-enabling `extra="forbid"` is
possible if `.env` and container environments are ever fully separated.
