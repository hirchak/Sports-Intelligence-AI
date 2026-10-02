# Current Task

**Task:** M9 independent-review blockers: immutable population and truthful proposal→experiment mapping.
**Status:** FIX IMPLEMENTED / LOCAL GATES PASS; exact-head CI pending. M9 NOT ACCEPTED.
**Branch:** build/m9
**Reviewed delivery:** 383c32f9ba5255f9c72d74c5e7c2ffbcdeba66fb.
**Accepted M8 main/tag:** 490227ac8e27ca4c8870891277fd8783d8a7f1af / annotated v0.9-m8.

Binding scope: [M9_REVIEW_FIX_SCOPE.md](M9_REVIEW_FIX_SCOPE.md), original [M9_SCOPE.md](M9_SCOPE.md).
Findings: broad planner inventory depends on mutable Fixture kickoff/league; default approval
creates candidate-prompt experiments for unrelated components. Small hardening: allow known football
identifiers while rejecting LLM-supplied numeric measurement claims.

Focused verification: 33 new integration PASS; 54 M9 contract unit PASS (20 new review-contract cases).
Reviewed planner with corrected setup reproduces both population count failures; reviewed approval has
false mappings; post-fix default/explicit/legacy/atomicity/Telegram regressions PASS. No schema changes.
Full local verification: **893 unit + 233 integration = 1126 full PASS**, 68.77s, zero skips.
Ruff/format247/mypy168; fresh + populated M8→M9 cycles/no drift; Compose default/dev/Telegram;
328-file/history secret sanity and diff checks PASS. Models/migrations/providers/forecast/evaluation/config unchanged.
Next: scoped commit/push build/m9, exact source/final CI, compact completed handoff; STOP for independent review.
No redesign, schema expansion, production application, merge/tag M9, M10, deployment/Hetzner/Hermes.
