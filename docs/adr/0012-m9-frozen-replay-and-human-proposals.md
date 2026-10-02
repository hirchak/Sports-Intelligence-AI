# ADR 0012 — Frozen replay, paired measurement and proposal-only improvement

Date: 2026-10-02. Status: Accepted with M9 independent PASS / ACCEPTED (2026-10-03).
Scope: LOCAL DEVELOPMENT ONLY; [M9_SCOPE.md](../M9_SCOPE.md).

## Context

Accepted M6 contexts and M7/M8 forecasts must stay immutable. A replay cannot rebuild
historical inputs using current data or contaminate production selection/evaluation.

## Decision

Separate experiment definitions/arms, runs, fixture cases, arm outputs, physical call ledger,
comparisons, proposals and proposal events. No experiment writes to production prediction,
prompt activation, model routing or evaluation rows. Reuse PredictionEngine, projection,
validator/ranking and M8 settlement/aggregate functions, rather than duplicate their math.

Freeze prompt content/hash, route/model configs, prediction/evaluation policy at definition creation.
Definitions cannot be updated; material changes require a new identity. Freeze ordered sample manifest
and result-version IDs at planning. Results enter deterministic evaluation only, never model payload.
Review-fix correction (2026-10-02): date scope means frozen prediction as_of [start,end).
Automatic population is the unique fixture identities of matching frozen MatchContexts only; it is not
an all-discovered-fixture census. Current Fixture kickoff/league/team/status metadata cannot define
population or denominators. Explicit fixture IDs retain requested cases with no historical contexts;
explicit context IDs keep strict identity/scope behavior. Counts disclose population_basis.

Both arms share one context unless phases explicitly differ; cross-phase comparison is observational.
Paired metrics use successful forecasts with the same settled selection on both arms; full-arm metrics
retain failures/abstentions/missing outcomes. Minimum sample counts independent fixture pairs,
not correlated market selections. Report measurements only, never significance or usable winner.

CAS claims prevent simultaneous duplicate arm calls. Physical retries/repairs reserve persisted budget
and ledger; completed outputs are never called again. Sequential bounded batches default to five
fixtures, effective experiment concurrency one. An interrupted RUNNING claim requires human inspection
and explicit rerun identity; automatically reclaiming it could duplicate an unknown paid call.
Known transient failures may resume under the same manifest with counted attempts.

Analyst consumes bounded stored comparison evidence through ModelRouter/provider abstraction.
Python supplies factual metrics, sample counts and IDs. Strict output permits qualitative proposal
fields only; no numeric measurement claims. Deduplicate by evidence and frozen analyst identity.
Review-fix correction: default approval is prompt-only and copies the control arm with the registered
candidate prompt as treatment. Before any persistence, frozen arms must show an actual prompt hash
change with identical model/config/phase/variant/policy, or an explicit reviewed model definition must
show an actual model/config change with identical prompt/phase/variant/policy. Historical arms cannot
prove this via their unused declared route, so mapping requires replay arms. Unsupported data_quality,
features, ranking and sources remain proposals; definitions in M9 cannot express those treatment changes.
No partial approval event/status/link on refusal. Existing incompatible links cannot advance to running
or promoted, and remain rejectable without rewriting history. Telegram consumes backend approval advice.
Known football labels H2H/1X2/O/U1.5/O/U2.5 are prose exceptions; measured numbers and extra facts remain forbidden.
Human approval creates an experiment authorization; execution is a separate explicit queue request.
PROMOTED/ROLLED_BACK, if recorded, are audit decisions requiring an actor/reason; no config application.
Weekly analysis is disabled by default, mock-only when enabled unless separately live-opted-in.

## Alternatives

Reuse production PredictionRun with extra scope filters: rejected to avoid missed production selectors.
Rebuild historical snapshots: rejected because absence is not evidence. New metric formulas: rejected.

## Consequences / rollback

M9 adds normalized tables only, Alembic 0014; downgrade removes M9 data, preserving M0–M8.
No fitted ensemble, production mutations, statistical significance, invented cost or provider backfill.
Existing WITHOUT_ODDS projection also masks research; disclose that limitation.
