# Current Task

**Task:** M9 — Experiments / Historical Replay / Model-Prompt Comparison / Improvement Proposals.
**Status:** IMPLEMENTED AND VERIFIED; STOP FOR INDEPENDENT REVIEW. Not independently accepted.
**Branch:** build/m9
**Verified runtime source:** `dff83c17e2eddcde08ca0a5676dcc9d516a4cf6c`.
**Exact runtime-source CI:** [37053961881](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/37053961881), all three jobs SUCCESS.

Accepted M8/M8.1 PASS/ACCEPTED; PR #10 merged; main `490227ac8e27ca4c8870891277fd8783d8a7f1af`;
annotated `v0.9-m8`; main CI `36981326405` all jobs SUCCESS. At startup build/m9/main/tag were identical.
Post-M8 state-doc drift corrected first; historical worklog preserved.

Completed: ADR 0012, migration 0014 (ten tables), exact frozen replay/historical arms, shared M8 metrics
and archived closing proxy, bounded evidence-bound analyst, human lifecycle, CLI/private API/thin Telegram.
Verified: **873 unit + 200 integration = 1073 full PASS**, 64.93s, zero skips. Ruff/format245/mypy168;
fresh and populated Alembic cycles/no drift; Compose default/dev/Telegram; secret sanity and diff checks PASS.
Real collectors→M9 keyless E2E, actual task wrappers, API/Telegram and all anti-leakage regressions PASS.

[M9 scope](M9_SCOPE.md), [method/API/CLI](EXPERIMENTS.md), [review receipt](REVIEW_HANDOFF.md).
Final documentation-only delivery HEAD/CI is checked after commit and reported in the completion message;
resolve `origin/build/m9` for the canonical tip. No runtime source changes after the verified source above.

**Next:** independent review only. M9 NOT MERGED/TAGGED; M10 NOT STARTED. LOCAL DEVELOPMENT ONLY.
Zero live LLM calls / deployment / Hetzner / Hermes interaction. No automatic production promotion.
