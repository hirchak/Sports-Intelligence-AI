# Deployment

## Status

**LOCAL DEVELOPMENT ONLY. No deployment is authorized.**

This document exists only so that a future phase has a clear starting point.

Authoritative references (future phase):

- `05_HETZNER_DEPLOYMENT_RUNBOOK.md`
- `13_LOCAL_DEV_TO_HETZNER_MIGRATION.md`
- `18_LOCAL_ACCEPTANCE_TEST_PLAN.md` (deployment gate)

## What must be true before any server deployment

- All local acceptance tests pass (`18_LOCAL_ACCEPTANCE_TEST_PLAN.md` §16).
- Independent audit: PASS or PASS WITH ACCEPTED ISSUES.
- Git tagged known-good version.
- Production secrets prepared outside the repository.
- DB decision made: start fresh or migrate local history via pg_dump/restore.

## Isolation requirements (already designed into M0)

- Separate compose project `sports-intel`, separate network/volumes/`.env`.
- No Hermes ports/volumes/names reused; Hermes untouched.
- Postgres/Redis bound to internal Docker network in production.
- Telegram long polling — no public webhook port.

## Explicitly out of scope until authorized

- SSH access to any server;
- remote Docker/Compose commands;
- automatic deployment pipelines;
- backup automation on the server.
