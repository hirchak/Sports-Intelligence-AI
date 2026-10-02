CONTINUATION OF THE ACTIVE M9 REVIEW-FIX GOAL.

M9 is NOT accepted yet. Fix only the following independent-review blockers and their regressions.

Accepted base remains:
main = 490227ac8e27ca4c8870891277fd8783d8a7f1af
v0.9-m8
M9 reviewed delivery HEAD:
383c32f9ba5255f9c72d74c5e7c2ffbcdeba66fb

Do not redesign M9.
Do not start M10.
Do not deploy.

============================================================
1. BLOCKER — HISTORICAL REPLAY POPULATION USES MUTABLE FIXTURE DATA
============================================================

Current planner uses the live/current `Fixture.kickoff_at` table to inventory fixtures in a historical date range when explicit fixture/context IDs are not supplied.

This is not acceptable for a frozen historical experiment.

Even if Fixture data is not passed to the predictor, later mutation/rescheduling can change:
- requested population
- non_replayable counts
- exclusion/reason counts
- experiment manifest identity
- analyst evidence packet

for the same historical experiment definition.

The historical replay population and its denominators must not depend on mutable current fixture truth.

Fix this using the simplest truthful design.

Requirements:

- Eligible replay inputs must continue to come from frozen MatchContext/evidence only.
- Do not use mutable current Fixture kickoff/team/league values to reconstruct historical population.
- If all-fixture historical population cannot be proven from immutable historical records, do not pretend it can.
- For a broad date-range replay, it is acceptable to define the automatic population as the frozen historical MatchContext population and document that denominator explicitly.
- Explicit `fixture_ids` may still identify requested fixtures and truthfully report missing frozen contexts.
- Explicit `context_ids` must retain current strict behavior.
- If there is an already-existing immutable historical fixture/discovery snapshot that can safely define population, it may be used, but do not create a new current-data backfill.
- Same frozen definition + same frozen historical state must give stable requested/eligible/non-replayable counts regardless of later mutations to `fixtures`.

Add regression tests that:
1. create historical frozen contexts;
2. plan replay;
3. mutate current Fixture kickoff/league/current metadata;
4. plan again;
5. assert historical replay population/counts/manifest-relevant selection are unchanged.

Also test an explicitly requested fixture without frozen context remains visible as NOT_REPLAYABLE without provider backfill.

============================================================
2. BLOCKER — PROPOSAL APPROVAL CAN AUTHORIZE AN UNRELATED EXPERIMENT
============================================================

Current `AnalystOutput.affected_component` permits:
- prompt
- model
- data_quality
- features
- ranking
- sources

But default `approve_experiment(..., experiment=None)` always clones the parent definition and changes only:

treatment.prompt = "candidate"

Telegram approval uses this default path.

Therefore a proposal such as:
- change ranking threshold
- change feature logic
- change source weighting
- change data-quality policy
- change model

can be linked to a candidate-prompt experiment that does not actually test the proposed change.

That creates false proposal → experiment lineage and later allows the proposal to reach EXPERIMENT_RUNNING/PROMOTED based on unrelated evidence.

Fix this fail-closed.

Requirements:

- Never auto-create an experiment that does not represent the approved proposal.
- Automatic/default approval may only be allowed when the proposal can be truthfully mapped to an implemented experiment dimension.
- At minimum, prompt proposals may map to the registered candidate prompt path.
- For model proposals, either map explicitly to a reviewed/configured model route or require an explicit reviewed ExperimentDefinition.
- For data_quality/features/ranking/sources proposals, do NOT silently convert them into prompt experiments.
- If M9 cannot directly instantiate that experimental change, approval must require an explicit reviewed experiment definition or return a clear “manual experiment definition required / unsupported automatic experiment mapping” result.
- Proposal status must remain PROPOSED if no truthful experiment can be created.
- Do not create `experiment_id`, approval event, or APPROVED status before experiment creation succeeds.
- Telegram must not show a generic “candidate prompt” approval action for proposal types it cannot truthfully map.
- UI should explain that a reviewed/manual experiment definition is required instead.

Add regression tests for every affected_component:
- prompt default approval creates the intended candidate-prompt experiment;
- unsupported automatic mappings fail closed;
- no status/event/experiment_id changes on rejected automatic mapping;
- explicit reviewed compatible ExperimentDefinition can be approved;
- experiment lineage reflects what was actually tested;
- no production mutation.

============================================================
3. SMALL HARDENING WHILE TOUCHING ANALYST CONTRACT
============================================================

Review the blanket AnalystOutput validation that rejects every digit in prose.

Do not weaken protection against fabricated measured metrics, but avoid unnecessarily rejecting legitimate football/domain identifiers such as:
- H2H
- 1X2
- O/U 1.5
- O/U 2.5

Keep factual measured values Python-authoritative.

If changing this safely requires broader redesign, document it and leave it for later; it is not the primary blocker.

============================================================
4. VERIFICATION
============================================================

Run all relevant focused regressions first.

Then full gates:

uv run ruff check .
uv run ruff format --check .
uv run mypy src

unit suite
integration suite
full pytest

Alembic:
fresh DB → head
downgrade -1
upgrade head
alembic check

Verify accepted M8 → M9 migration path still passes.

docker compose config -q
docker compose -f compose.yaml -f compose.dev.yaml config -q
docker compose --profile telegram config -q

secret sanity
git diff --check

Update:
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md append-only
- docs/REVIEW_HANDOFF.md
- docs/EXPERIMENTS.md if semantics changed

Push build/m9.

Wait for GitHub Actions on the exact final remote HEAD.
All jobs must be SUCCESS.

============================================================
5. FINAL STATE
============================================================

Do not merge M9.
Do not tag M9.
Do not create/start M10.
No deployment / Hetzner / Hermes.

Return:
- final build/m9 HEAD
- exact CI run
- exact frozen-population fix
- exact proposal→experiment lineage fix
- new regression tests
- unit/integration/full counts
- lint/type/migration/compose results
- known limitations

Then STOP for independent review.