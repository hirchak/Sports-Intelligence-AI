# Current Task

**Task:** Finalize independently accepted Milestone M7
**Independent verdict:** M7 / M7.1 = PASS / ACCEPTED
**Status:** Documentation finalization and PR-to-main flow in progress
**Branch:** `build/m7`
**Accepted HEAD:** `3c75d09676d84e31a2f6d5b0265cd9b629f87f9b`
**M7.1 implementation:** `07658d8e9fdd29f0e642447fd1639efb0b08aa47`
**Accepted source CI:** `36911970853` — SUCCESS, all three jobs
**Accepted base/main:** `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` (`v0.7-m6`)

## Binding scope

The user provided the independent M7 / M7.1 PASS / ACCEPTED verdict. Finalize docs, commit and push
docs-only changes, open PR `build/m7` → `main`, wait for PR checks, merge with the established normal
merge strategy, verify final main and its CI, create/push annotated `v0.8-m7` on merged main, then
create/push a clean `build/m8` from that exact main SHA. Do not implement anything on `build/m8`.

Remain LOCAL DEVELOPMENT ONLY. No Hetzner/deployment/Hermes. M8 settlement/evaluation NOT STARTED.
Preserve all historical failed/review verdicts in status and append-only worklog.

## Previously verified M7 acceptance

- 535 unit PASS; 128 integration PASS; 663 total PASS.
- Ruff/format/myPy clean; Alembic clean; Compose clean.
- Accepted `origin/build/m7` HEAD and final source CI are listed above.
- Main and `v0.7-m6` remain on the accepted M6 SHA until the authorized PR is merged.

## Next action

Commit/push docs-only finalization, wait for exact-head CI, create the requested PR, and continue only through
the authorized merge/tag/build/m8 setup. Stop on `build/m8` without code changes.
