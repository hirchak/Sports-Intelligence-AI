# Future deployment only

**LOCAL DEVELOPMENT ONLY. M10 performs no deployment and authorizes none.**
No SSH/Hetzner/server inspection, remote Docker, automatic delivery pipeline, public infrastructure change
or Hermes interaction is part of this milestone. The deployment gate can remain NOT READY while local
implementation is complete. Current evidence: M10_ACCEPTANCE_REPORT and PRODUCTION_READINESS.

## Reproducible private topology

Future approved operations may validate `compose.yaml` + `compose.production-example.yaml` (Compose
>=2.24.4). The example removes API/Postgres/Redis host ports with !reset, uses production API command,
INFO logging, application uid10001, restart policies and log rotation. Telegram remains long polling.
Set a dedicated Compose project, protected separate env, database/credentials, project-scoped network
and persistent Postgres/Redis volumes. Never combine with compose.dev.yaml. No outside container/network/
volume/database is referenced; no existing application is required or inspected by this repository.

Production secrets must replace public local-development defaults. Provider/model IDs, leagues, fixture
scope, schedules, quota reserve and physical LLM budgets remain operator configuration. Optional/live
experiment/analyst switches must remain explicit; no change follows automatically from an approved proposal.
The private API is not safe to publish merely because localhost tests pass.

## Later explicit authorization must resolve

- Independent M10 review PASS (or accepted issues), exact known-good code/tag, complete required local gates.
- Real sports/odds/search/model/Telegram integration evidence as applicable; no mock-to-live inference.
- Production secret preparation/rotation, intended live league/fixture/budget/notification configuration.
- Fresh DB versus historical-data transfer decision; native backup/restore, counts and immutable hashes.
- Actual target capacity, volume space, conflicts/isolation and security checks **at that future time**.
- Controlled start/rollback ownership and protected nightly backup retention/restore plan.

M10 does not inspect any target or create cron there. Historical master deployment specs remain future-phase
references, subordinate to the current no-server/no-deployment lock. A green CI alone is not authorization.
