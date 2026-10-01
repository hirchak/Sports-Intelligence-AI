# ADR 0010 — M7 forecasting semantics and separate market comparison

Status: implemented under the explicit M7 scope, pending independent milestone review.
Date: 2026-10-01. Scope: LOCAL DEVELOPMENT ONLY. No M8/deployment.

The existing architecture already requires immutable MatchContext and deterministic scheduling/math.
M7 preserves those boundaries and records these implementation decisions:

- Freeze prompt content, model/route and prediction/ranking policy at enqueue, not worker execution.
- Unique request hash plus optional explicit rerun UUID; CAS worker claim; terminal records not overwritten.
- Actual fallback/returned model has its own config and semantic identity. Requested route remains auditable.
- One repair across all configured routes; physical retry/repair calls each reserve daily budget and telemetry.
- Separate twelve model probabilities, considered ranked candidates and independent baseline records.
- Unfitted independent Poisson using available last10 scoring/conceding rates; missing rates stay unavailable.
- DC market benchmark derives from captured same-bookmaker 1X2; overlapping DC probabilities cannot sum to 1.
- WITHOUT_ODDS masks arbitrary research text/provenance/quality detail conservatively, preserving original DB
  context. Later comparisons must acknowledge that this also removes research evidence.
- Existing MORNING/PREMATCH phases remain unchanged. Context completion is the opt-in automatic trigger.

These are scoped, reversible configuration/application choices, not changes to accepted M0–M6 authority.
No fitted ensemble, result truth, evaluation/calibration, auto-promotion or live operation is introduced.
Operational limitation: worker crash after claim or lost broker message requires inspection/explicit rerun;
automatic reset would risk repeating paid calls without evidence of whether the first request completed.
