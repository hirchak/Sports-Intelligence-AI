> **Scope history:** this file preserves the original implementation handoff verbatim. Its final “not merged/tagged” stop applied before independent review. The owner has since supplied M10 PASS / ACCEPTED and explicitly authorized the separate release closeout recorded in [CURRENT_TASK.md](CURRENT_TASK.md) and [REVIEW_HANDOFF.md](REVIEW_HANDOFF.md). Deployment remains unauthorized/NOT READY, and no M11 is defined.

# Binding M9 closeout and M10 scope

CONTINUATION OF THE ACTIVE GOAL.

Everything below is binding.

You are the lead implementation agent for:
1. finalizing independently ACCEPTED M9;
2. creating build/m10 from the accepted merged M9 state;
3. implementing M10 Production Readiness;
4. stopping for independent M10 review.

This is still LOCAL DEVELOPMENT ONLY.

ABSOLUTELY NO:
- Hetzner connection;
- SSH;
- server inspection;
- deployment;
- Hermes interaction;
- remote Docker commands;
- public infrastructure changes.

M10 prepares and verifies the project for future deployment.
It does NOT perform deployment.

======================================================================
0. VERIFY CURRENT REPOSITORY STATE
======================================================================

First read:

- AGENTS.md
- README_EXECUTION_ORDER.md
- 00_MASTER_TECHNICAL_SPEC.md
- docs/IMPLEMENTATION_STATUS.md
- docs/CURRENT_TASK.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md
- docs/ARCHITECTURE.md
- docs/DATA_MODEL.md
- docs/PIPELINES.md
- docs/TELEGRAM.md
- docs/LOCAL_DEVELOPMENT.md
- docs/DEPLOYMENT.md
- docs/SECURITY.md
- docs/EXPERIMENTS.md
- 10_DATABASE_AND_DATA_LIFECYCLE.md
- 11_API_QUOTA_CACHING_STRATEGY.md
- 12_LLM_ROUTER_AND_MODEL_POLICY.md
- 14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md
- 15_FORECASTING_METHODOLOGY_V1.md
- 16_GITHUB_AI_DEVELOPMENT_CONTROL.md
- 17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md
- 18_LOCAL_ACCEPTANCE_TEST_PLAN.md
- all accepted ADRs

Inspect:

git status
git branch --show-current
git fetch origin
git rev-parse HEAD
git rev-parse origin/build/m9
git rev-parse origin/main
git tag --list

Expected accepted M9 review HEAD:

354c8f5ff27fe5427313a459937c17054073f36a

Independent review verdict:
M9 / M9 review-fix = PASS / ACCEPTED.

Exact accepted CI:
37061920047
all three jobs SUCCESS.

Accepted M8 main before M9 merge:
490227ac8e27ca4c8870891277fd8783d8a7f1af
tag v0.9-m8.

If repository reality differs from this, inspect and reconcile safely.
Do not infer state from chat memory.

======================================================================
1. FINALIZE ACCEPTED M9
======================================================================

Record the independent PASS / ACCEPTED verdict in persistent state docs.

Preserve historical FAIL/review entries.
AI_WORKLOG remains append-only.

Then:

1. commit/push any docs-only acceptance receipt if needed;
2. wait for exact-head CI;
3. create PR build/m9 → main;
4. wait for all PR checks;
5. merge using the repository's existing merge-commit strategy;
6. fetch/update local main;
7. verify exact merged main SHA;
8. wait for merged-main CI and require all jobs SUCCESS;
9. create an annotated M9 tag following established repository version sequence;
   expected sequence is v0.10-m9, but verify current tag convention before creating it;
10. push tag;
11. verify tag peels to exact accepted merged main commit;
12. create and push build/m10 from that exact same merged main SHA;
13. verify:

origin/build/m10 == origin/main == M9-tag^{}

Do not begin M10 source changes until the M9 closeout is verified.

Record exact:
- PR number
- merge SHA
- main CI run
- tag object/peeled commit
- build/m10 SHA

======================================================================
2. M10 OBJECTIVE
======================================================================

M10 = Production Readiness.

Primary scope:

- security pass;
- backup/restore;
- restart/recovery verification;
- resource checks;
- operational readiness;
- configuration safety;
- complete local E2E;
- clean bootstrap;
- deployment documentation;
- final v1 documentation;
- deployment-gate evidence;
- independent review handoff.

Do not redesign the forecasting architecture.

Prefer boring, auditable operational engineering.

======================================================================
3. IMPORTANT DISTINCTION — M10 VS DEPLOYMENT
======================================================================

M10 should answer:

"Is this repository and local runtime ready for a later controlled deployment?"

It must NOT answer by actually deploying.

A deployment gate may remain NOT READY if a required live integration cannot
truthfully be exercised locally.

Never fake a green gate.

Track every gate as one of:

PASS
FAIL
NOT_VERIFIED
NOT_APPLICABLE

with evidence.

M10 code may be implementation-complete while the deployment gate remains
blocked by genuinely unverified live credentials/integrations.

Do not hide this distinction.

======================================================================
4. CLEAN BOOTSTRAP
======================================================================

Prove the repository can be recreated without AI-chat context.

Use an isolated clean local checkout/worktree/temp directory.

Verify documented bootstrap from repository sources only:

- copy/create local env from .env.example without exposing secrets;
- dependency install from locked dependencies;
- Docker Compose startup;
- fresh PostgreSQL;
- Redis;
- Alembic upgrade to head;
- league/config seed command;
- API;
- worker;
- beat;
- Telegram profile/config validation;
- /health;
- /ready.

No manual DB hacking.

If a documented bootstrap command is missing or unreliable, fix it.

README + LOCAL_DEVELOPMENT must be sufficient for a new engineer.

======================================================================
5. COMPLETE MOCK END-TO-END V1
======================================================================

Create or verify a deterministic keyless M0→M10 acceptance path:

fixture discovery
→ sports collectors
→ odds
→ research
→ data quality
→ features
→ immutable MatchContext
→ MockLLM prediction
→ validation
→ ranking
→ Telegram/test transport
→ result injection/collection
→ deterministic settlement
→ evaluation
→ M9 replay/experiment
→ improvement proposal

Expected:
- deterministic;
- no external credentials;
- no hidden network calls;
- CI-compatible;
- old immutable prediction/context evidence unchanged.

This should become an explicit local acceptance command/test if not already one.

======================================================================
6. SCHEDULER / UNATTENDED PIPELINE READINESS
======================================================================

Verify automatic-first behavior.

At minimum verify scheduling/planning for:

- fixture discovery;
- collector refreshes;
- research;
- MatchContext;
- predictions;
- result scans;
- evaluation;
- optional M9 improvement schedule.

Test with deterministic/frozen time where practical.

Verify:
- repeated scheduler scans do not duplicate semantic work;
- prediction jobs remain idempotent;
- completed results are not repeatedly reprocessed unsafely;
- retries are bounded;
- disabled optional services degrade safely.

Do not run multi-day wall-clock tests if unnecessary.
A representative deterministic/accelerated schedule simulation is acceptable.

If true multi-day unattended operation is not actually observed, document it as
not empirically proven rather than claiming otherwise.

======================================================================
7. RESTART / RECOVERY TEST
======================================================================

Perform a local recovery test.

During representative queued/persisted work, exercise local restarts of:
- API
- worker
- beat where relevant
- Telegram service/profile where practical

Verify:
- PostgreSQL state survives;
- Redis loss/restart does not corrupt canonical DB truth;
- completed predictions are not duplicated;
- jobs remain auditable;
- retry/recovery semantics are explicit;
- Telegram remains stateless relative to core work.

Do not invent a new distributed recovery platform.

If existing known limitations require manual inspection/rerun, document them.

======================================================================
8. DATABASE BACKUP / RESTORE
======================================================================

Implement/document and actually test a LOCAL backup/restore workflow.

Use PostgreSQL-native dump/restore.

Requirements:

- pg_dump;
- compressed format where appropriate;
- safe temporary backup destination;
- no secrets in filename/log output;
- clean temporary restore DB;
- pg_restore;
- verify schema;
- compare meaningful row counts;
- verify at least one immutable MatchContext hash;
- verify at least one PredictionRun and associated identity;
- verify result/evaluation/experiment records where available;
- cleanup temporary DB/files.

Provide simple scripts/Make targets/commands if useful.

Production documentation should specify MVP conceptually:

- nightly pg_dump;
- compressed;
- configurable retention, e.g. 7 daily;
- protected backup location;
- tested restore procedure.

Do NOT configure any remote cron/server.

======================================================================
9. SECURITY PASS
======================================================================

Perform a repository/runtime security review.

Verify/fix at minimum:

- Telegram allowlist cannot be bypassed;
- no arbitrary shell execution exposed through Telegram/API;
- API arguments validated;
- no API keys accepted through unsafe public user inputs;
- secrets only from environment/local secret mechanisms;
- no secrets in Git history;
- logs redact auth headers/tokens/keys;
- provider error logging is safe;
- LLM metadata does not persist secrets;
- DB/Redis are not publicly exposed by intended production configuration;
- local ports are loopback only where intended;
- containers run non-root where practical;
- production-like debug/reload behavior disabled;
- dependencies are locked;
- no permissive CORS/public control-plane exposure accidentally added;
- backup artifacts are not committed;
- .env ignored;
- database dumps ignored;
- dangerous admin actions require authorization;
- improvement system still cannot modify production automatically.

Do not add a complex auth platform.
This remains a private system.

======================================================================
10. PRODUCTION CONFIGURATION SAFETY
======================================================================

Review configuration behavior for MOCK / SANDBOX / LIVE_LOCAL and future
production-like deployment.

Ensure:

- MOCK stays keyless;
- no silent Mock fallback in non-mock modes;
- required credentials fail clearly;
- production-like configuration cannot accidentally enable debug/reload;
- provider/model IDs remain configuration-driven;
- Telegram allowlist required;
- unsafe empty allowlist behavior fails closed where applicable;
- result/prediction/improvement schedules are explicitly configurable;
- live experiment/analyst gates remain explicit;
- quotas and reserve behavior remain configurable.

Do not require production server credentials.

======================================================================
11. NETWORK / COMPOSE READINESS
======================================================================

Review Docker/Compose for future isolated deployment.

Without deploying, verify the repository supports/documented design for:

- separate Compose project;
- separate containers;
- separate network;
- separate volumes;
- separate database;
- separate .env;
- no Hermes dependency;
- no Hermes container/network/volume names;
- PostgreSQL/Redis not publicly exposed in production-like configuration;
- API not publicly exposed unless explicitly intended;
- Telegram long polling initially;
- persistent Postgres volume;
- restart policies where appropriate;
- healthchecks where useful.

A production Compose example/override may be added if that is the cleanest way
to make configuration reproducible.

It must contain no real credentials and must not be executed remotely.

======================================================================
12. OBSERVABILITY / OPERATIONS
======================================================================

Audit existing observability and close practical gaps.

Ensure operationally useful visibility for:

- health/readiness;
- correlation ID;
- job ID;
- fixture ID;
- prediction run ID;
- experiment run ID where relevant;
- provider failures;
- quota/degradation state;
- LLM latency/token usage when available;
- job/task duration;
- failed jobs;
- result/evaluation failures.

Do not introduce Prometheus/Grafana or heavy infrastructure unless already
justified by repository specs.

Structured logs + DB operational state are sufficient for v1 if complete.

Create/update a concise operational runbook covering:

- start
- stop
- restart
- health verification
- queue/worker verification
- failed-job investigation
- database backup
- restore
- rollback concept
- secret rotation concept
- provider quota incident
- Redis failure
- PostgreSQL failure
- Telegram failure

======================================================================
13. RESOURCE / CAPACITY TEST
======================================================================

Run a representative LOCAL workload.

Record evidence such as:

- Docker container CPU;
- RAM;
- PostgreSQL DB size;
- Redis memory;
- worker concurrency;
- rough log volume;
- representative batch duration;
- number of fixtures/jobs where applicable.

Prefer a bounded representative batch rather than wasting hours.

Use this only as local sizing evidence.

Do NOT claim exact Hetzner sizing from one synthetic test.

Document:
- measured local numbers;
- environment/machine caveat;
- what still needs to be checked immediately before future deployment.

Do not inspect the Hetzner server now.

======================================================================
14. LIVE PROVIDER SMOKE GATE
======================================================================

The local acceptance plan includes a live provider smoke test.

Do this ONLY if valid credentials already exist locally.

Never print secret values.
Never ask the user to paste them into chat.

If sports/odds/search runtime credentials are present:

perform a very small bounded LOCAL smoke test using one fixture/date where safe.

Verify:
- successful request;
- raw payload persisted;
- normalized data persisted;
- request/quota metadata captured;
- immediate repeat uses caching/freshness and avoids duplicate unnecessary calls.

Keep external quota use minimal.

If credentials are absent or provider conditions make a safe smoke impossible:

mark:
LIVE_PROVIDER_SMOKE = NOT_VERIFIED

This is NOT permission to deploy or to fake PASS.

======================================================================
15. RUNTIME LLM SMOKE GATE
======================================================================

If a valid real runtime LLM credential/route is ALREADY configured locally,
perform at most one tightly bounded schema-valid prediction smoke on a suitable
existing MatchContext.

Verify:
- provider/model identity;
- structured output validation;
- persistence;
- no secret logging;
- usage/latency if provider returns it.

Do not evaluate forecasting quality from one prediction.

If unavailable:
REAL_LLM_SMOKE = NOT_VERIFIED

Mock E2E remains mandatory regardless.

======================================================================
16. TELEGRAM ACCEPTANCE
======================================================================

Run complete mocked/test-transport Telegram acceptance:

- unauthorized user rejected;
- /today;
- fixture detail;
- refresh/analyze;
- duplicate action safety;
- prediction;
- evidence/risks/model metadata;
- results;
- stats;
- experiments;
- improvements;
- health;
- pagination;
- malformed backend response;
- safe user-facing failure.

If a real bot token and safe local allowlisted test user are already configured,
a minimal LOCAL live Telegram smoke may be performed.

Do not spam.
Do not change Telegram credentials.

If not possible, clearly distinguish:
TEST_TRANSPORT_TELEGRAM = PASS
LIVE_TELEGRAM_SMOKE = NOT_VERIFIED

======================================================================
17. FAILURE / DEGRADATION ACCEPTANCE
======================================================================

Verify representative failure cases:

Sports/search/odds provider:
- timeout
- 429
- retryable 5xx
- malformed JSON
- invalid auth

LLM:
- timeout
- provider unavailable
- malformed structured output
- invalid probability
- repair failure

Infrastructure:
- Redis unavailable
- PostgreSQL unavailable
- provider quota conserve/critical/reserve-only modes

Expected:
- bounded retries;
- no tight loops;
- correct classification;
- auditable job state;
- no malformed forecast publication;
- safe Telegram/API status;
- critical work preserved according to policy.

======================================================================
18. QUOTA / COST CONTROLS
======================================================================

Audit existing quota/request controls rather than rewriting them.

Verify:

- request counters;
- request ledger;
- cache/freshness reuse;
- coalescing;
- no obvious N+1 regression;
- reserve quota;
- degradation modes;
- enabled leagues configurable;
- fixture scope bounded;
- LLM daily/challenger/experiment budgets;
- token usage recorded when available;
- unknown monetary cost remains unknown rather than fabricated.

======================================================================
19. DATA INTEGRITY / REPRODUCIBILITY FINAL AUDIT
======================================================================

Create a final regression/audit verifying that a stored forecast can still be
reconstructed from:

- fixture ID;
- MatchContext ID/hash;
- as_of;
- feature version;
- source snapshot identities;
- odds identity;
- data-quality report;
- prompt identity/hash/version;
- model/provider/config identity;
- prediction probability records.

Verify M8 settlement/evaluation references original prediction truth.

Verify M9 replay continues to use frozen historical contexts only.

No current/future row may alter an old prediction identity.

======================================================================
20. DOCUMENTATION COMPLETION
======================================================================

Repository must be usable without old ChatGPT/Codex conversations.

Audit and complete at minimum:

README.md
docs/ARCHITECTURE.md
docs/DATA_MODEL.md
docs/PIPELINES.md
docs/TELEGRAM.md
docs/LOCAL_DEVELOPMENT.md
docs/DEPLOYMENT.md
docs/SECURITY.md
docs/IMPLEMENTATION_STATUS.md
docs/CURRENT_TASK.md
docs/AI_WORKLOG.md
docs/REVIEW_HANDOFF.md
docs/EXPERIMENTS.md
docs/adr/

Add/update operational documentation as needed, e.g.:

docs/OPERATIONS.md
docs/BACKUP_RESTORE.md
docs/PRODUCTION_READINESS.md

Do not duplicate stale contradictory instructions.

Deployment docs must clearly state:
future deployment only, requires explicit user authorization.

======================================================================
21. LOCAL ACCEPTANCE REPORT
======================================================================

Create a persistent M10 deployment/readiness matrix based on
18_LOCAL_ACCEPTANCE_TEST_PLAN.md.

For every gate record:

- status
- exact command/test
- evidence
- limitations
- date
- relevant commit

At minimum:

clean bootstrap
mock E2E
live sports provider
batch/no-N+1
prediction reproducibility
no leakage
Telegram test transport
live Telegram if available
provider failures
LLM failures
settlement
evaluation
quota degradation
restart/recovery
backup/restore
resource test
secret scan
independent review status

Do not mark independent audit PASS yourself.

======================================================================
22. CI / AUTOMATION
======================================================================

Improve CI only where it gives stable useful assurance.

CI must remain keyless.

Require at minimum current gates:
- Ruff;
- format;
- mypy;
- unit;
- integration;
- migration consistency;
- Compose config.

If M10 adds deterministic bootstrap/backup/security checks that are safe and
reasonably fast, add them to CI or a dedicated script.

Do not make CI depend on:
- live APIs;
- Telegram network;
- Hetzner;
- external LLM credentials.

======================================================================
23. NO FAKE PRODUCTION READINESS
======================================================================

Final output must distinguish:

A. IMPLEMENTATION READY
B. LOCAL ACCEPTANCE VERIFIED
C. LIVE INTEGRATIONS VERIFIED
D. DEPLOYMENT GATE READY

Example:

if mock/local infrastructure is perfect but no live provider smoke exists:

M10 implementation may be complete,
but DEPLOYMENT GATE = NOT READY
because LIVE_PROVIDER_SMOKE remains NOT_VERIFIED.

This is correct behavior.

Do not bend criteria to produce a green badge.

======================================================================
24. FULL VERIFICATION GATES
======================================================================

Run full repository gates:

uv run ruff check .
uv run ruff format --check .
uv run mypy src

unit suite
integration suite
full pytest

Alembic:
fresh DB → upgrade head
downgrade -1
upgrade head
alembic check

Verify populated accepted M9 → latest migration integrity.
If M10 requires no schema changes, prove migration history remains clean.

Compose:
docker compose config -q
docker compose -f compose.yaml -f compose.dev.yaml config -q
docker compose --profile telegram config -q
plus any new production-example config validation.

Secret/history sanity.
git diff --check.

Run:
- clean bootstrap acceptance;
- mock full E2E;
- backup/restore;
- restart/recovery;
- security checks;
- representative resource measurement.

Push build/m10.

Wait for GitHub Actions on the exact final remote HEAD.
All required CI jobs must be SUCCESS.

======================================================================
25. FINAL M10 STATE
======================================================================

At handoff:

- branch = build/m10
- build/m10 pushed
- working tree clean
- main remains accepted merged M9
- M9 tag remains unchanged
- M10 NOT merged
- M10 NOT tagged
- no M11
- zero deployment
- zero Hetzner interaction
- zero Hermes interaction

STOP for independent review.

Do not merge/tag M10 yourself.

======================================================================
26. FINAL HANDOFF FORMAT
======================================================================

Return a concise but complete handoff with:

1. M9 PR number
2. M9 merged main SHA
3. M9 merged-main CI
4. M9 annotated tag + peeled SHA
5. build/m10 base confirmation
6. final build/m10 HEAD
7. exact M10 CI run
8. security audit summary
9. clean bootstrap result
10. mock E2E result
11. scheduler/unattended simulation result
12. restart/recovery result
13. backup/restore result
14. resource test measurements
15. production-like Compose/network safety
16. observability/runbook changes
17. quota/cost-control verification
18. reproducibility/leakage final audit
19. Telegram test-transport result
20. live Telegram smoke status
21. live sports/odds/search smoke status
22. real runtime LLM smoke status
23. deployment/readiness matrix
24. unit count
25. integration count
26. full test count
27. Ruff/format/mypy
28. Alembic results
29. Compose results
30. secret/history scan
31. remaining NOT_VERIFIED gates
32. deployment gate verdict: READY / NOT READY with exact reasons
33. confirmation M10 not merged/tagged
34. confirmation no M11
35. confirmation zero deployment / Hetzner / Hermes interaction

Then STOP for independent review.