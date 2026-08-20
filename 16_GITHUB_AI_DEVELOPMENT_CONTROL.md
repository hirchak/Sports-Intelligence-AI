# GitHub + AI Development Control Workflow

The AI coding agent is powerful, but Git is the control system.

The repository must always make it possible for another engineer/model to audit what happened.

---

# 1. Branch strategy

For a solo project, keep it simple.

```text
main
  stable / accepted milestones

build/m0
build/m1
...
feature/<name>
fix/<name>
```

The lead agent may work on a milestone branch.

Merge to `main` only after tests/review.

If using one branch initially, at minimum create clean milestone commits/tags.

---

# 2. Commit strategy

Good:

```text
M0: scaffold repository and local Docker stack
M1: add Postgres migrations and Celery infrastructure
M2: implement API-Football fixture discovery adapter
```

Bad:

```text
changes
fix stuff
final
final2
```

No giant unrelated commits.

---

# 3. Required repo status file

Maintain:

```text
docs/IMPLEMENTATION_STATUS.md
```

It must be updated every milestone.

This is the entry point for ChatGPT/Kimi/other reviewers.

---

# 4. Decision records

Use ADRs:

```text
docs/adr/0001-use-celery.md
docs/adr/0002-sports-provider.md
docs/adr/0003-odds-source.md
...
```

ADR format:

```text
Context
Decision
Alternatives
Consequences
Rollback/Migration
```

---

# 5. AI agent handoff protocol

Every fresh coding session reads:

1. `00_MASTER_TECHNICAL_SPEC.md`
2. `README_EXECUTION_ORDER.md`
3. `docs/IMPLEMENTATION_STATUS.md`
4. relevant detailed spec;
5. relevant ADRs;
6. current tests.

The agent must not rely on previous chat memory.

---

# 6. Milestone gate

Before beginning next milestone:

```text
working tree clean
tests green
lint green
migrations valid
implementation status updated
known issues documented
commit created
```

Then review.

---

# 7. Independent review

After major milestones, reviewer receives:

```text
master spec
detailed relevant specs
current Git commit
implementation status
```

Reviewer checks code, not only agent summary.

---

# 8. Change request format

When review finds issue, create a focused task:

```markdown
## Problem
...

## Evidence
file:line / test failure

## Required behavior
...

## Constraints
...

## Acceptance test
...
```

Give this to DeepSeek/MiniMax.

Avoid vague:

```text
make it better
```

---

# 9. Secret scan

Before every push/release:

- `.env` ignored;
- scan Git diff;
- optional secret-scanning tool;
- no SSH/API key in docs/tests/log fixtures.

If a key is accidentally committed, rotate it even if commit is deleted later.

---

# 10. Tags

Useful milestones:

```text
v0.1-m0
v0.2-local-fixtures
v0.3-local-prediction
v0.4-evaluation
v1.0-local-accepted
v1.0-server
```

Names can vary.

---

# 11. Server deployment source

Server should run a known Git commit/tag.

Do not edit production source manually without committing the equivalent change.

---

# 12. ChatGPT review handoff

When asking an external reviewer to inspect progress, provide:

- repository/access;
- current commit hash;
- current milestone;
- `docs/IMPLEMENTATION_STATUS.md`;
- what specifically should be reviewed.

Useful review scopes:

```text
architecture
database/migrations
API adapter/quota
Telegram
prediction methodology
security
deployment
full milestone
```

---

# 13. Development control acceptance criteria

- [ ] Stable code state identifiable by commit.
- [ ] Every architecture deviation has ADR.
- [ ] Milestone status exists.
- [ ] Tests run before milestone completion.
- [ ] Secrets absent.
- [ ] Another model can continue without old chat.
