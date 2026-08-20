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
- Pydantic `extra="forbid"` rejects unknown environment variables to catch
  configuration typos early.
- Telegram bot token is NOT validated by `Settings` in M0: the bot is a
  separate process (M3) and will validate its own requirements. This is a
  deliberate relaxation to keep the API usable in sandbox without a bot token.

## Alternatives

- Validating the Telegram token at Settings level now — rejected: the API and
  bot are separate processes; coupling them at config level would block
  sandbox API-only work.

## Consequences

- `docker compose up` works out of the box with `.env.example` (mock mode).
- Misconfiguration fails fast with actionable messages.

## Rollback/Migration

Adding stricter mode requirements later (e.g. require bot token in
`live_local`) is a config-only change.
