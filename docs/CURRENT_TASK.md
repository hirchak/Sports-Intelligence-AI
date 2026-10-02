# Current Task

**Task:** M9 independent-review blockers — immutable replay population, truthful proposal mapping.
**Status:** REVIEW FIX COMPLETED / VERIFIED; STOP FOR INDEPENDENT REVIEW. M9 NOT ACCEPTED.
**Branch:** build/m9
**Reviewed delivery:** 383c32f9ba5255f9c72d74c5e7c2ffbcdeba66fb.
**Verified fix source:** 642dd3690919cbb3dfed8b37a2ac089b74e3a308.
**Exact source CI:** [37061295354](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/37061295354), all three jobs SUCCESS.
**Accepted M8 main/tag:** 490227ac8e27ca4c8870891277fd8783d8a7f1af / annotated v0.9-m8, unchanged.

Binding scope: [M9_REVIEW_FIX_SCOPE.md](M9_REVIEW_FIX_SCOPE.md). Methods: [EXPERIMENTS.md](EXPERIMENTS.md).

Completed: automatic population exclusively from frozen matching contexts, explicit requested missing IDs
preserved; population_basis visible. Prompt-only default compares control with candidate prompt under same
model/config. Model approval requires explicit compatible reviewed definition. Unsupported/no-op/mixed/
historical-declared mappings refuse before experiment/event/status/link writes. Legacy wrong links cannot
advance/reapprove/promote and remain rejectable. Telegram consumes typed approval advice, no misleading
automatic action. H2H/1X2/O/U labels allowed, LLM-supplied measurements/extra factual fields still rejected.

Verified: 20 new unit + 33 new integration regressions; **893 unit + 233 integration = 1126 full PASS**,
68.77s, zero skips. Ruff/format247/mypy168; fresh DB head/down -1/head/check and populated M8→M9
roundtrip/no drift; Compose default/dev/Telegram; 328-file/history secret sanity and diff checks PASS.
No schema, migration, provider, prediction/evaluation math, prompts or runtime configuration changes.

Limits: broad population is captured contexts, not all fixtures; unsupported component treatments stay
outside M9. Older immutable results are not rewritten; explicit rerun uses fixed planner. Human review
owns qualitative intent. Live integrations/empirical merit are unproven, zero real LLM calls this fix.

Final documentation-only delivery HEAD/CI is verified after commit and supplied in the completion message;
resolve origin/build/m9 for canonical tip. No source changes after the verified fix above.
Next: independent review only. No merge/tag M9, M10, deployment/Hetzner/Hermes; LOCAL DEVELOPMENT ONLY.
