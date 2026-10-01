# Current Task

**Task:** M7.1 — Align M7 baselines/ranking with the accepted M4 `h2h_1x2` contract
**Status:** IMPLEMENTED / FULL LOCAL ACCEPTANCE PASS — commit/push/exact CI pending
**Branch:** `build/m7`
**Reviewed start:** `b0dd35c3606449d95c3be0723ded5f78a2883e67`
**Base/main:** `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` (`v0.7-m6`)

## Binding scope

M4 persists normalized `h2h_1x2` with `home/draw/away`; M7 must accept and group the actual canonical values.
Verify complete same-bookmaker 1X2 grouping and DC derivations; add M4-identifier regressions and align
M7 synthetic fixtures. Do not redesign M4 or architecture. Do not start M8, merge/tag M7, deploy,
use Hetzner or interact with Hermes. Remain LOCAL DEVELOPMENT ONLY.

## Verification checkpoint (2026-10-01 18:54 UTC)

- M7 baseline/grouping accepts canonical `h2h_1x2`; legacy `h2h` / `1x2` aliases remain supported.
- Complete no-vig 1X2 is grouped per identified bookmaker. DC market rows are ignored as benchmarks;
  HOME_OR_DRAW / HOME_OR_AWAY / DRAW_OR_AWAY derive from that bookmaker's full 1X2.
- Incomplete 1X2 and selections split across bookmakers do not produce an M7 1X2/DC baseline.
- M7 fixture and keyless E2E M4 mock output now exercise canonical `h2h_1x2`. Raw provider request key `h2h` unchanged.
- Full suite: **535 unit + 128 integration = 663 passed**. Ruff/format/mypy passed; Compose passed;
  `alembic check` reports no new upgrade operations. Focused M7 E2E also passed after mock alignment.
- No DB schema or migrations changed; no real runtime LLM calls.
- `docs/AI_WORKLOG.md` records this acceptance pass.

## Next action

Commit and push the M7.1 fix to `build/m7`, verify all CI jobs on exact remote HEAD, update handoff,
then STOP for independent review. M7 remains unmerged; M8 is not started.
