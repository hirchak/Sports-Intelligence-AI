# M10 v1 readiness contract

LOCAL DEVELOPMENT ONLY. M10 is operational engineering and evidence for a **later explicitly authorized**
deployment; it performs none. Binding scope: M10_SCOPE. Exact receipts: M10_ACCEPTANCE_REPORT.

Distinguish:

A. IMPLEMENTATION READY — scoped operational changes, documented commands, tests/static/migrations/CI complete.
B. LOCAL ACCEPTANCE VERIFIED — clean bootstrap, full keyless pipeline, scheduler simulation, recovery,
   native restore and local resource measurements passed with recorded limits.
C. LIVE INTEGRATIONS VERIFIED — each genuine sports/odds/search/LLM/Telegram smoke separately evidenced.
D. DEPLOYMENT GATE READY — all required local/live/independent-review/known-good-version gates satisfied.

A/B do not imply C/D. Every gate is PASS, FAIL, NOT_VERIFIED or NOT_APPLICABLE, with command/evidence,
date, commit and limitation. Implementation-agent security work never marks independent audit PASS.
M10 independent review is PASS / ACCEPTED. Missing runtime LLM/odds credentials and the failed sports smoke
remain live blockers; the deployment gate is NOT READY.

## v1 operational limits

- Frozen-time three-day planning/duplicate tests and a bounded actual queued batch do not establish several
  uninterrupted real-world days. Multi-day empirical operation remains NOT_VERIFIED.
- Redis loss preserves canonical Postgres truth but may lose delivery and quota reservations. Unknown paid
  RUNNING attempts require inspection/new rerun, never automatic claim reset. No new recovery platform.
- Local Docker Desktop CPU/RAM/DB/Redis/log measurements are snapshots, not exact server sizing or peaks.
- Mock forecasts/analyst proposals prove engineering contracts, not quality/profit/calibration/superiority.
- Monetary cost remains unknown if providers do not supply it. Current contexts/quotes cannot repair absent
  historical evidence; M9 captured-context population is not an all-fixture census.
- WITHOUT_ODDS also removes research, so no pure causal odds-only claim.
- Public API exposure, target resources/security, production credentials/backups and controlled rollback
  remain future explicitly approved operations. No M11 starts here.

README/LOCAL_DEVELOPMENT recreate the system without chat history. OPERATIONS and BACKUP_RESTORE
cover start/stop/restart/health/queue/failures/quotas/data/secrets/rollback. SECURITY records implementation
findings; M10 was independently accepted PASS / ACCEPTED. Main and v0.10-m9 stay unchanged until the authorized M10 merge/tag closeout.
