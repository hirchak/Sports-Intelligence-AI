# OpenCode Multi-Model Workflow
## Suggested agent organization for this project

This document is optional. The repository must not depend on OpenCode to run.

OpenCode is a development tool only.

The production sports system uses its own runtime LLM provider configuration.

---

# Recommended development roles

## `architect`

Purpose:
- read-only architecture and planning;
- review data model;
- review boundaries;
- write implementation plan.

Suggested model:
- GLM-5.2 or GLM-5.3

Permissions:
- read/search allowed;
- edits denied by default;
- shell denied or ask.

Prompt source:
- `01_GLM_5_2_ARCHITECT_REVIEWER.md`

## `lead`

Purpose:
- primary build agent;
- integrate milestones;
- maintain status docs;
- Git commits.

Suggested model:
- DeepSeek V4 Pro

Permissions:
- edit allowed;
- shell allowed;
- Git allowed;
- destructive server actions denied.

Prompt source:
- `02_DEEPSEEK_V4_PRO_LEAD_ENGINEER.md`

## `implementer`

Purpose:
- scoped coding tasks.

Suggested model:
- MiniMax M3

Prompt source:
- `03_MINIMAX_M3_IMPLEMENTER.md`

## `auditor`

Purpose:
- independent audit/debugging.

Suggested model:
- Kimi K3

Prompt source:
- `04_KIMI_K3_AUDITOR_DEBUGGER.md`

---

# Example conceptual OpenCode configuration

Adapt to the current OpenCode schema and model IDs shown by `/models`.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "architect": {
      "mode": "primary",
      "model": "opencode-go/glm-5.2",
      "prompt": "{file:./01_GLM_5_2_ARCHITECT_REVIEWER.md}",
      "permission": {
        "edit": "deny",
        "bash": "deny"
      }
    },
    "lead": {
      "mode": "primary",
      "model": "opencode-go/deepseek-v4-pro",
      "prompt": "{file:./02_DEEPSEEK_V4_PRO_LEAD_ENGINEER.md}",
      "permission": {
        "edit": "allow",
        "bash": "allow"
      }
    },
    "implementer": {
      "mode": "subagent",
      "description": "Implements scoped Sports Intelligence tasks with tests",
      "model": "opencode-go/minimax-m3",
      "prompt": "{file:./03_MINIMAX_M3_IMPLEMENTER.md}"
    },
    "auditor": {
      "mode": "subagent",
      "description": "Independently audits architecture, tests, security and data leakage",
      "model": "opencode-go/kimi-k3",
      "prompt": "{file:./04_KIMI_K3_AUDITOR_DEBUGGER.md}"
    }
  }
}
```

The exact OpenCode config schema/model availability can change. Verify using current docs and `/models` before committing configuration.

---

# Cost-conscious usage

Do not use the most expensive reasoning model for every repetitive edit.

A sensible pattern:

```text
Architect/reviewer
        ↓
Lead creates a precise task
        ↓
Implementer writes scoped code
        ↓
Lead integrates and runs tests
        ↓
Auditor reviews milestone
```

This is more reliable than repeatedly handing the complete repository to a fresh model with a vague prompt.

---

# Context hygiene

At every milestone, maintain repository documents so agents do not depend on chat memory:

- `00_MASTER_TECHNICAL_SPEC.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/adr/*`
- tests
- Git history

For a new model session:

1. read master spec;
2. read implementation status;
3. inspect relevant code;
4. read relevant ADRs;
5. perform only the assigned role.

---

# Runtime model vs development model

Do not confuse them.

**Development model**
- writes/reviews the software in OpenCode.

**Runtime prediction model**
- receives MatchContext and predicts football-market probabilities when the application is running.

They can be the same vendor/model, but they are separate concerns and separate configuration.

The runtime prediction engine must be swappable and evaluated empirically using stored forecasts.
