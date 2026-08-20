# Prompt to Start DeepSeek V4 Pro

Before doing anything else:

1. Read `AGENTS.md` and treat it as mandatory project rules.
2. Read `docs/IMPLEMENTATION_STATUS.md`.
3. Read `docs/CURRENT_TASK.md`.
4. Confirm that the current phase is **LOCAL DEVELOPMENT ONLY**.
5. Do not deploy, SSH, access Hetzner, or interact with Hermes.

Persistent state requirements:

- update `docs/CURRENT_TASK.md` before starting implementation;
- update `docs/IMPLEMENTATION_STATUS.md` after meaningful progress and before commit;
- append a concise entry to `docs/AI_WORKLOG.md`;
- update `docs/REVIEW_HANDOFF.md` when M0 is ready for review.

The repository state files are the persistent memory of the project. Do not rely on prior chat/session memory.

---

Paste the following instruction into the first build session after placing the specification pack in the repository.

---

You are the lead engineer for this repository.

First, read these files completely:

1. `00_MASTER_TECHNICAL_SPEC.md`
2. `README_EXECUTION_ORDER.md`
3. `02_DEEPSEEK_V4_PRO_LEAD_ENGINEER.md`
4. `07_TELEGRAM_BOT_SPEC.md`
5. `08_FOOTBALL_ANALYTICS_PIPELINE.md`
6. `09_AGENT_CATALOG_AND_ORCHESTRATION.md`
7. `10_DATABASE_AND_DATA_LIFECYCLE.md`
8. `11_API_QUOTA_CACHING_STRATEGY.md`
9. `12_LLM_ROUTER_AND_MODEL_POLICY.md`
10. `13_LOCAL_DEV_TO_HETZNER_MIGRATION.md`
11. `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`
12. `15_FORECASTING_METHODOLOGY_V1.md`
13. `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`
14. `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`
15. `18_LOCAL_ACCEPTANCE_TEST_PLAN.md`

Treat these documents as the product/engineering requirements.

Do **not** deploy anything to Hetzner yet.

Do **not** modify or depend on Hermes.

Do **not** attempt to implement the entire system in one pass.

Your first task is M0 only.

Before changing files:

1. inspect the repository;
2. identify any contradictions among the specification documents;
3. propose the exact M0 repository structure;
4. list assumptions;
5. create any necessary ADRs for M0;
6. create `docs/IMPLEMENTATION_STATUS.md`.

Then implement M0.

M0 must include at minimum:

- Python project scaffold;
- dependency lock;
- FastAPI skeleton;
- Docker/Compose development scaffold;
- PostgreSQL/Redis service definitions;
- config/settings validation;
- logging foundation;
- test structure;
- CI skeleton;
- documentation structure;
- `.env.example`;
- Git hygiene;
- mock-mode design.

Do not implement fake "complete" integrations in M0.

Run the required tests/lint/type checks.

At the end:

1. update `docs/IMPLEMENTATION_STATUS.md`;
2. show tests/checks and their results;
3. list deviations/assumptions;
4. commit the completed M0 milestone to Git with a meaningful commit message;
5. stop and wait for review before M1.
