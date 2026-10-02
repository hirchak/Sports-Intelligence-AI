# Current Task

**Task:** M8.1 acceptance fix — persisted EvaluationRun selection for summary reads.
**Status:** IN PROGRESS; reviewed M8 blocker supplied by owner.
**Branch:** build/m8
**Reviewed HEAD:** d56aa3620f728eae500a1d95bce167c986d3dfda.
**Accepted main/tag:** 4eff88bcaaac387ec047d50575d25b8135baa567 / v0.8-m7.

Scope: prefer compatible scoped materializations for combined filters / filter + group_by;
preserve cutoff ordering among equally suitable runs; return not_available when the persisted
materializations cannot answer. Add regressions A–D and full acceptance gates.
No changes to metric formulas, settlements, result collection, M7, or schema.
LOCAL DEVELOPMENT ONLY. Authorized commits/push build/m8 and exact-head CI verification.
No M9, merge/tag M8, deployment, Hetzner/Hermes/server interaction.

Next: reproduce scoped-run shadowing, implement selection fix, run requested full gates,
update exact verified source/CI receipts and stop for independent review.
