# Persistent Agent State System
## Why these files exist and how they work together

OpenCode automatically uses a root-level `AGENTS.md` as project instructions.

For this project, persistent continuity is split into four different concerns rather than one giant state file.

---

# 1. `AGENTS.md` — rules

Stable project operating rules.

Changes rarely.

Contains:
- local-only phase lock;
- Git behavior;
- testing rules;
- architecture guardrails;
- required state updates;
- security;
- milestone discipline.

Think of it as the project's constitution.

---

# 2. `docs/IMPLEMENTATION_STATUS.md` — current truth

Current high-level state.

Changes frequently.

Answers:
- which milestone?
- what is complete?
- what is not verified?
- what is blocked?
- what commit is current?
- what is next?

This is the first file a reviewer reads after `AGENTS.md`.

---

# 3. `docs/CURRENT_TASK.md` — active task

Short-lived work focus.

Answers:
- what is the agent doing right now?
- what is in/out of scope?
- what acceptance criteria apply?

This prevents context drift inside long coding sessions.

---

# 4. `docs/AI_WORKLOG.md` — historical log

Append-only history.

Answers:
- what happened in earlier sessions?
- what tests were run?
- which model/agent did it?
- what commit resulted?
- what problems were discovered?

Do not use it as the current-state file.

---

# 5. `docs/REVIEW_HANDOFF.md` — reviewer packet

Updated when a milestone/task is ready for independent review.

Answers:
- what exactly should be reviewed?
- which commit?
- what does the implementation agent claim passed?
- what known limitations exist?

This allows another model to audit the project without re-reading the full chat history.

---

# 6. Update cadence

## Before coding

Update:
- `CURRENT_TASK.md`

Read:
- `AGENTS.md`
- `IMPLEMENTATION_STATUS.md`

## During meaningful work

Append only when useful:
- `AI_WORKLOG.md`

Do not log every trivial edit.

## Before commit

Update:
- `IMPLEMENTATION_STATUS.md`
- `CURRENT_TASK.md`
- `AI_WORKLOG.md`

## Before review

Update:
- `REVIEW_HANDOFF.md`

---

# 7. Git

All five files are committed.

This makes state travel with the repository and makes rollback/review possible.

The state files must never contain:

- secrets;
- API tokens;
- passwords;
- SSH data;
- personal server credentials.

---

# 8. Local-only phase lock

Current phase is:

```text
LOCAL DEVELOPMENT ONLY
```

Changing to deployment requires an explicit user decision.

When that happens:

1. update `AGENTS.md`;
2. update `IMPLEMENTATION_STATUS.md`;
3. create deployment task;
4. perform production preflight;
5. only then use the Hetzner runbook.

Possessing deployment documentation is not authorization to deploy.
