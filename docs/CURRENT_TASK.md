# Current Task

**Task:** M9 — Experiments / Historical Replay / Model-Prompt Comparison / Improvement Proposals.
**Status:** IMPLEMENTED; full final gates and exact remote CI in progress.
**Branch:** build/m9

M8 / M8.1 = PASS / ACCEPTED. PR #10 merged; accepted main `490227ac8e27ca4c8870891277fd8783d8a7f1af`.
Annotated tag `v0.9-m8`; merged-main CI `36981326405`, all three jobs SUCCESS on exact SHA (verified).
Startup after fetch: build/m9 == origin/build/m9 == origin/main == v0.9-m8^{} == accepted main.
M9 now ACTIVE under [M9_SCOPE.md](M9_SCOPE.md); M9 not merged/tagged; M10 NOT STARTED.
LOCAL DEVELOPMENT ONLY; no deployment / Hetzner / Hermes interaction.

State-doc drift corrected first; historical worklog preserved.
Implemented: ADR 0012, migration 0014 (ten tables), frozen replay/historical-arm reuse, M8 metrics,
bounded analyst, human lifecycle, CLI/private API/thin Telegram. [EXPERIMENTS.md](EXPERIMENTS.md).
Verified: 873 unit PASS; 200 integration PASS; actual task wrappers and keyless M2→M9 E2E PASS.
Ruff/format/strict mypy, fresh/populated Alembic cycles/no drift, Compose default/dev/Telegram,
325-file/history secret sanity, accepted migrations/prediction/production prompt byte identity PASS.
Final full pytest: 1073 PASS, 64.93s; Ruff/format/mypy and all local gates complete.
Initial source 84a257ddf96241428d1ab4b57e641f4e7f6b604f / CI 37051194076 all jobs SUCCESS.
Closing proxy uses the shared M8 formula and explicit historical comparators; long valid abstention
text is preserved in output with stable short reason code. Final source commit/push/CI next.
Final gate: full local checks, push build/m9, exact-head CI SUCCESS, clean tree; STOP for independent review.
