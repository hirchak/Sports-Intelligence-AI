# Current Task

**Task:** M8.1 acceptance fix — persisted EvaluationRun selection for summary reads.
**Status:** COMPLETE — implementation and local/remote acceptance checks PASS; independent review required.
**Branch:** build/m8; M8 not merged/tagged, M9 not started. LOCAL DEVELOPMENT ONLY.
**Reviewed starting HEAD:** d56aa3620f728eae500a1d95bce167c986d3dfda.
**Verified implementation HEAD:** 248e6b190faf4d5b232b7f6eb60a67510c57ae86.
**Verified CI:** 36976617246 — all 3 jobs SUCCESS (lint/type/unit, integration, Compose).
**Accepted main/tag:** 4eff88bcaaac387ec047d50575d25b8135baa567 / v0.8-m7, unchanged.

Fixed: prefer compatible scoped materializations for combined filters / filter + group_by;
more covered requested scope before cutoff recency; unsupported combinations return not_available.
Five regression tests cover A–D, equal-scope recency and legitimate partial scopes.
No metric formulas, settlement rules, collectors, M7, schema or migration changes.

Verified: 839 unit + 151 integration = 990 full pytest; Ruff/format/mypy clean;
Alembic fresh/head/down -1/head/check plus populated-cycle tests; Compose default/dev/Telegram;
working-file/history secret sanity. All verification is complete; historical pending notes in the
append-only worklog are superseded by this checkpoint and the completed CI receipt.

Documentation closeout contains no runtime/test changes. The final checkout SHA is the Git tip;
its exact delivery CI receipt is canonical in GitHub Actions and returned in the completion message.
Read-only lookup: `git rev-parse HEAD`; `gh run list --branch build/m8 --limit 1 --json headSha,databaseId,conclusion`.

Next: STOP for independent review. No further implementation, M9, merge/tag, deployment or server work.
