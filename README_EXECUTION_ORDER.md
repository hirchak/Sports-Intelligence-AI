# Sports Intelligence AI — Engineering Pack

This folder is the authoritative implementation handoff for a private football forecasting platform.

The safest workflow is:

```text
specification
→ architecture review
→ milestone implementation
→ tests
→ independent audit
→ local live testing
→ Hetzner deployment
```

Do not ask one model to "build everything" in one uncontrolled pass.

---


# Persistent AI control files

Before any coding session, OpenCode should use/read:

- `AGENTS.md` — permanent project rules and LOCAL-ONLY phase lock
- `docs/IMPLEMENTATION_STATUS.md` — current project state
- `docs/CURRENT_TASK.md` — exact active task
- `docs/AI_WORKLOG.md` — append-only engineering history
- `docs/REVIEW_HANDOFF.md` — compact packet for independent review

See `20_PERSISTENT_AGENT_STATE_SYSTEM.md`.


# Document map

## Core

### `00_MASTER_TECHNICAL_SPEC.md`
Authoritative top-level architecture and product requirements.

### `README_EXECUTION_ORDER.md`
This file. Read first.

---

# Development-model roles

### `01_GLM_5_2_ARCHITECT_REVIEWER.md`
Read-only architecture/planning review.

### `02_DEEPSEEK_V4_PRO_LEAD_ENGINEER.md`
Primary lead engineer instructions.

### `03_MINIMAX_M3_IMPLEMENTER.md`
Scoped coding worker instructions.

### `04_KIMI_K3_AUDITOR_DEBUGGER.md`
Independent milestone audit/debug instructions.

### `05_HETZNER_DEPLOYMENT_RUNBOOK.md`
Production deployment beside Hermes.

### `06_OPENCODE_MULTI_MODEL_WORKFLOW.md`
Optional OpenCode agent organization.

---

# Detailed product/engineering specifications

### `07_TELEGRAM_BOT_SPEC.md`
Bot screens, buttons, commands, flows, notifications and security.

### `08_FOOTBALL_ANALYTICS_PIPELINE.md`
What data to collect for each football match and the end-to-end analytical flow.

### `09_AGENT_CATALOG_AND_ORCHESTRATION.md`
Exact agent/service roles, inputs/outputs, DAG, queues and retries.

### `10_DATABASE_AND_DATA_LIFECYCLE.md`
PostgreSQL schema, immutable snapshots, retention and laptop→server data movement.

### `11_API_QUOTA_CACHING_STRATEGY.md`
Batching, quota manager, caching, request coalescing and degradation modes.

### `12_LLM_ROUTER_AND_MODEL_POLICY.md`
OpenCode Go / MiniMax / OpenAI provider abstraction, routing, fallbacks and challengers.

### `13_LOCAL_DEV_TO_HETZNER_MIGRATION.md`
Local Docker workflow and production migration.

### `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`
`as_of`, source provenance, conflicts, missingness and anti-leakage tests.

### `15_FORECASTING_METHODOLOGY_V1.md`
Measurement-first prediction methodology, baselines, calibration and experiments.

### `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`
Git branches/commits/ADRs and AI handoff/review process.

### `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`
What is decided, what is provisional and what must remain configurable.

### `18_LOCAL_ACCEPTANCE_TEST_PLAN.md`
Deployment gate and exact local tests.

### `19_PROMPT_TO_START_DEEPSEEK.md`
Ready-to-paste first instruction for DeepSeek V4 Pro.

---

# Recommended model workflow

## Simplest

Use **DeepSeek V4 Pro** as the lead engineer for the entire implementation.

Give it all spec files and `19_PROMPT_TO_START_DEEPSEEK.md`.

Use another model only for independent review.

This is the least confusing workflow.

## Multi-model

Optional:

```text
GLM-5.2/5.3
  architecture review

DeepSeek V4 Pro
  lead/integration

MiniMax M3
  scoped implementation

Kimi K3
  independent audit/debug
```

The exact model lineup can change.

The repository/specification is more important than any one model.

---

# Milestone order

```text
M0 architecture/repo
M1 core infrastructure
M2 sports provider + fixture discovery
M3 Telegram base UI
M4 match collectors + odds + quota management
M5 web research
M6 features + MatchContext + quality
M7 LLM prediction + ranking
M8 settlement + evaluation
M9 experiments + improvement proposals
M10 production readiness
```

The detailed specs should be implemented as relevant milestones are reached.

---

# Golden rules

1. OpenCode is a development environment, not the production architecture.
2. Production runtime LLMs are called through provider adapters.
3. OpenCode Go may be one runtime provider through its documented API endpoints.
4. Telegram is a UI, not the core.
5. Scheduler/orchestrator is deterministic code.
6. Do not use LLM for market settlement or basic math.
7. Every forecast is reproducible from immutable pre-match evidence.
8. No future data may leak into historical replay.
9. API calls are budgeted and cached.
10. Improvement analysis cannot silently mutate production.
11. GitHub contains code/config/migrations, not database volumes/secrets.
12. Hermes stays separate.

---

# Start here

Place all `.md` files in the repository root (or a dedicated `spec/` directory if DeepSeek updates references consistently).

Then use:

`19_PROMPT_TO_START_DEEPSEEK.md`

Do not provide Hetzner credentials until local acceptance testing is complete.
