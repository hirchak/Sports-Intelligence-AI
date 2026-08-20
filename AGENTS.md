# AGENTS.md
## Sports Intelligence AI — Project Rules for Coding Agents

This file is the persistent operating contract for every AI coding session in this repository.

These rules apply to DeepSeek, MiniMax, Kimi, GLM and any other coding agent unless the user explicitly overrides them.

---

# 1. Current development phase

**PHASE: LOCAL DEVELOPMENT ONLY**

Until the user explicitly changes this phase:

- do not deploy to Hetzner;
- do not SSH into any server;
- do not ask for server credentials;
- do not run `scp`, `rsync`, remote Docker commands or remote migration commands;
- do not modify, restart, inspect or depend on Hermes;
- do not expose new public infrastructure;
- do not create automatic deployment pipelines.

Hetzner documentation exists only for a future phase.

All implementation, tests, databases, Redis, workers and Telegram development must run locally through Docker Compose.

---

# 2. Mandatory session startup

At the beginning of every new coding session:

1. Read this `AGENTS.md`.
2. Read `docs/IMPLEMENTATION_STATUS.md`.
3. Read `docs/CURRENT_TASK.md`.
4. Read the relevant specification files for the current task.
5. Inspect `git status` and recent Git history.
6. Verify the current milestone before making changes.

Do not rely on memory from a previous AI chat/session.

If `docs/IMPLEMENTATION_STATUS.md` conflicts with the repository, trust code/tests/Git evidence and update the status file.

---

# 3. Authoritative specifications

Top-level authority:

- `00_MASTER_TECHNICAL_SPEC.md`

Detailed specifications:

- `07_TELEGRAM_BOT_SPEC.md`
- `08_FOOTBALL_ANALYTICS_PIPELINE.md`
- `09_AGENT_CATALOG_AND_ORCHESTRATION.md`
- `10_DATABASE_AND_DATA_LIFECYCLE.md`
- `11_API_QUOTA_CACHING_STRATEGY.md`
- `12_LLM_ROUTER_AND_MODEL_POLICY.md`
- `13_LOCAL_DEV_TO_HETZNER_MIGRATION.md`
- `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`
- `15_FORECASTING_METHODOLOGY_V1.md`
- `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`
- `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`
- `18_LOCAL_ACCEPTANCE_TEST_PLAN.md`

Model-role instructions are secondary to product specifications.

If two specs conflict:

1. stop changing the conflicting area;
2. document the conflict in `docs/IMPLEMENTATION_STATUS.md`;
3. prefer the safer/reversible interpretation;
4. create an ADR if an architectural decision is required.

---

# 4. Milestone discipline

Implement one milestone at a time.

Current milestone is recorded in:

`docs/IMPLEMENTATION_STATUS.md`

Do not silently start the next milestone.

Before marking a milestone complete:

- relevant tests pass;
- lint passes;
- type checks pass where configured;
- migrations are valid;
- documentation is updated;
- implementation status is updated;
- worklog entry is appended;
- Git working tree is understood;
- a meaningful commit is created.

---

# 5. Persistent project memory

The repository, not chat history, is the persistent memory.

Maintain these files continuously:

## `docs/IMPLEMENTATION_STATUS.md`

Canonical current state.

Update:
- after every meaningful task;
- before every milestone commit;
- before handing work to another model/reviewer.

## `docs/CURRENT_TASK.md`

The exact task currently being executed.

Update:
- before beginning a task;
- when scope changes;
- mark complete when done.

## `docs/AI_WORKLOG.md`

Append-only engineering log.

Append:
- after a meaningful implementation session;
- after important debugging;
- after a milestone review;
- after any architecture deviation.

Never rewrite old worklog entries to make history look cleaner.

## `docs/REVIEW_HANDOFF.md`

A compact handoff for another reviewer.

Update before requesting external review or moving to the next milestone.

---

# 6. Worklog minimum entry

Every entry in `docs/AI_WORKLOG.md` must include:

```text
timestamp
agent/model if known
milestone
task
files changed
behavior implemented
commands/tests run
results
known problems
spec/ADR deviations
Git commit hash if created
next recommended action
```

Do not paste huge terminal logs.

Summarize them and reference files/tests.

---

# 7. Git rules

Git is the control plane for development history.

Required:

- small coherent commits;
- meaningful commit messages;
- no secrets;
- no database volumes;
- no generated caches;
- no `.env`;
- no force push unless explicitly authorized.

Before committing:

```text
git status
git diff
tests
lint
type checks
secret sanity check
```

Before a risky refactor, create a clean checkpoint commit.

Do not modify unrelated user files.

---

# 8. Architecture guardrails

Do not casually redesign these boundaries:

```text
Telegram UI
    ↓
application/control layer
    ↓
orchestrator/jobs
    ↓
collectors/providers
    ↓
PostgreSQL snapshots
    ↓
deterministic features
    ↓
MatchContext
    ↓
LLM prediction
    ↓
deterministic validation/ranking
    ↓
persistence/publishing
```

Rules:

- Telegram contains no prediction/business logic.
- Orchestrator is deterministic.
- LLM is not the scheduler.
- LLM does not settle results.
- LLM does not calculate basic odds math.
- Providers are behind adapters.
- MatchContext is immutable after prediction.
- Every prediction has `as_of`.
- Historical replay cannot use future data.
- Improvement agents cannot silently mutate production.

---

# 9. API/quota rules

Never implement N+1 external API calls when data can be:

- fetched in bulk;
- reused from a league snapshot;
- reused from a team snapshot;
- computed from local historical data;
- cached inside its freshness window.

Before adding a provider call, answer:

1. What entity owns this data?
2. Can it be fetched once for many fixtures?
3. What is its freshness window?
4. Is it already in PostgreSQL?
5. Is another worker already fetching it?
6. What quota priority does it have?

All provider calls must be observable in the request ledger.

---

# 10. Database rules

PostgreSQL is the runtime source of truth.

Never commit DB data to Git.

Required:

- Alembic migration for schema changes;
- UUID internal IDs;
- provider IDs stored separately;
- UTC timestamps;
- immutable prediction evidence;
- raw payload deduplication by hash where applicable;
- indexed fixture/date/odds/job access paths.

Do not manually edit a production-like DB schema outside migrations.

---

# 11. Local environment rules

The default environment is local Docker Compose.

Expected local modes:

```text
MOCK
SANDBOX
LIVE_LOCAL
```

MOCK must be usable without real external API keys.

Do not make CI depend on live sports/LLM providers.

---

# 12. Testing rules

Deterministic logic must have deterministic tests.

High-priority tests:

- market settlement;
- no-vig probability;
- EV and edge;
- probability validation;
- data-quality rules;
- task idempotency;
- quota/cache behavior;
- historical leakage;
- provider normalization;
- migrations.

A feature is not complete just because it "worked once manually."

---

# 13. Security rules

Never:

- commit credentials;
- print secrets;
- embed tokens in code;
- expose Redis/Postgres publicly;
- add arbitrary shell execution to Telegram;
- weaken authorization for convenience.

If a secret is accidentally committed, flag it immediately and recommend rotation.

---

# 14. Scope control

Do not add:

- Kubernetes;
- Kafka;
- public SaaS accounts;
- payments;
- live betting execution;
- unnecessary dashboards;
- vector databases;
- extra sports;

unless explicitly approved.

Prefer a boring, testable implementation.

---

# 15. Decision protocol

For reversible implementation detail:
- choose the simplest safe option;
- record assumption.

For significant architectural change:
- write ADR first.

For unresolved product choice:
- make it configuration if possible;
- do not hard-code an irreversible assumption.

---

# 16. Completion protocol for every task

Before saying a task is complete:

1. verify code;
2. run relevant tests;
3. update `docs/CURRENT_TASK.md`;
4. update `docs/IMPLEMENTATION_STATUS.md`;
5. append `docs/AI_WORKLOG.md`;
6. update `docs/REVIEW_HANDOFF.md` if review-ready;
7. commit if task/milestone is intended to be committed;
8. report exact remaining limitations.

Never claim "done" if tests were not run or an integration was only mocked.

---

# 17. Communication style for coding agents

Be concise and evidence-based.

When reporting progress, use:

```text
Completed
Verified
Not verified
Known issues
Next action
```

Do not bury failures.

Do not claim a live integration works when only unit tests passed.

---

# 18. Stop conditions

Stop the affected work and report if:

- a spec contradiction would cause irreversible architecture;
- a destructive migration is required unexpectedly;
- a secret appears in Git;
- a command could affect Hermes/server during LOCAL DEVELOPMENT phase;
- tests reveal data leakage;
- provider semantics are uncertain enough to corrupt stored data.

Continue unrelated safe work when possible.
