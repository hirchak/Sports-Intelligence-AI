# Review Handoff: M6.3 Reproducibility and Historical-Authority Pass

**Milestone:** M6.3 — Reproducibility and Historical-Authority Pass
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)
**Implementation Commit:** `5fb6c604617c7f93117e6d42d623a92082461981`
**Remote Status:** Pushed to `origin/build/m6`
**GitHub Actions Run:** `36831445894` (SUCCESS)
**Development Phase:** LOCAL DEVELOPMENT ONLY (No Hetzner, no SSH, no Hermes, no deployment, no M7, no LLM calls)

---

## 1. Final Remote HEAD SHA
- Implementation commit: `5fb6c604617c7f93117e6d42d623a92082461981`
- Matches `origin/build/m6`.

---

## 2. List of M6.3 Source Files Actually Committed
The following 16 files were committed in `5fb6c604617c7f93117e6d42d623a92082461981`:

### Source Files (11):
1. `src/sports_intelligence/collectors/freshness.py`
2. `src/sports_intelligence/context/builder.py`
3. `src/sports_intelligence/context/errors.py`
4. `src/sports_intelligence/context/models.py`
5. `src/sports_intelligence/context/provenance.py`
6. `src/sports_intelligence/context/selector.py`
7. `src/sports_intelligence/db/migrations/versions/0010_m6_3_freshness_policy.py`
8. `src/sports_intelligence/db/models/context.py`
9. `src/sports_intelligence/quality/engine.py`
10. `src/sports_intelligence/workers/tasks/context.py`
11. `src/sports_intelligence/workers/tasks/pre_match.py`

### Test Files (5):
12. `tests/integration/test_m6_anti_leakage_and_context.py`
13. `tests/unit/context/test_context_schema_and_hash.py`
14. `tests/unit/features/test_features_math.py`
15. `tests/unit/quality/test_quality_config_validation.py`
16. `tests/unit/quality/test_quality_engine.py`

---

## 3. Confirmation of Staged Diff Before Commit
Confirmed: `git diff --cached --stat` before commit contained all 16 files with 1,150 insertions and 197 deletions across both `src/` (502 insertions) and `tests/` (648 insertions). No files were missed.

---

## 4. Historical Missing-Metadata Behavior
- When no `FixtureMetadataSnapshot` exists with `captured_at <= as_of`:
  - `build_match_context()` raises typed exception `HistoricalFixtureMetadataUnavailable(fixture_id, as_of)`.
  - Context building refuses to copy mutable canonical `Fixture` fields (kickoff, status, team IDs, league ID, venue).
  - No `FeatureSnapshot`, `DataQualityReport`, or `MatchContext` is persisted for that historical evaluation.
  - Celery context task catches `HistoricalFixtureMetadataUnavailable`, logs a structured warning, and marks the task safely without unhandled exception tracebacks.
  - For as_of after migration 0009 backfill timestamp, the `legacy_baseline` snapshot is used with provenance noting `source_version="legacy_baseline"`. It is never backdated.

---

## 5. Metadata Team-ID Propagation
- All downstream evidence selection strictly uses `fixture_info.home_team_id` and `fixture_info.away_team_id` from the authoritative `FixtureMetadataSnapshot`.
- Provider entity mapping queries (`ProviderEntityId`) filter by `internal_id IN (fixture_info.home_team_id, fixture_info.away_team_id)`.
- Standings, team stats, form, player availability, and lineups queries filter strictly by `fixture_info.home_team_id` and `fixture_info.away_team_id`.
- Regression verified: If T0 metadata says teams A/B and later canonical Fixture is edited to A/C, historical context as_of T0 selects B evidence only and never selects C evidence.

---

## 6. Provider Mapping Provenance
- `select_evidence` captures all resolved `ProviderEntityId` mappings observed `<= as_of_utc`.
- Captured under `provider_mappings` section of the `source_manifest` with fields: `provider`, `internal_id`, `external_id`, `entity_type`, and `first_seen_at`.
- Historical isolation: if an entity was not mapped until after `as_of`, it is excluded from the historical mapping snapshot.

---

## 7. Canonical Source Manifest Fingerprint
- The source manifest dictionary (fixture metadata, evidence snapshots, and provider mappings) is sorted recursively and serialized via `canonical_json()`.
- SHA-256 hash is computed as the canonical `source_fingerprint`.
- Guarantees that any change in evidence snapshots, metadata snapshot, or provider mappings deterministically alters the `source_fingerprint`.

---

## 8. Freshness-Policy Snapshot + Fingerprint
- Introduced `FreshnessPolicy` dataclass in `collectors/freshness.py`.
- Encapsulates TTL configurations across all evidence types (standings, team stats, odds, injuries, lineups, research) and forecast phases (e.g. `MORNING`, `AFTERNOON`, `LINEUPS`, `LIVE`).
- `freshness_policy_snapshot` dictionary provides canonical representation.
- Computes SHA-256 `freshness_policy_fingerprint`.
- Migration `0010_m6_3_freshness_policy.py` adds `freshness_policy_fingerprint` to `data_quality_reports` table and extends unique constraint `uq_data_quality_reports_identity`.

---

## 9. Quality Identity
- `QualityPolicy` computes deterministic SHA-256 `policy_fingerprint`.
- Bound in `data_quality_reports` table.
- Composite unique constraint `uq_data_quality_reports_identity` spans:
  `(fixture_id, phase, as_of, schema_version, source_fingerprint, policy_fingerprint, freshness_policy_fingerprint)`.
- Different quality or freshness policies for the same evidence and `as_of` produce distinct reports and persist safely without collision.

---

## 10. ContextBuildPolicy
- `ContextBuildPolicy` combines `QualityPolicy` and `FreshnessPolicy`.
- Passed into `build_match_context()` and `build_and_persist_match_context()`.
- Computes `build_config_fingerprint` combining schema versions, policy fingerprint, freshness policy fingerprint, and research capability flag.
- Pre-match scanner constructs Celery job idempotency key:
  `context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}`.

---

## 11. Freshness-Generation Behavior
- Staleness penalties applied deterministically via `QualityPolicy.staleness_penalty` and `QualityPolicy.max_staleness_penalty`.
- Missing evidence dimensions penalized according to policy weights.
- MORNING phase lineups are strictly marked N/A: excluded from quality score denominator, omitted from `stale_sources`, and trigger zero staleness penalty.

---

## 12. Strict MatchContext Nested Schemas
- `MatchContextV1` and all 13 nested section models configured with Pydantic `ConfigDict(extra="forbid", frozen=True)`:
  - `FixtureSection`
  - `LeagueSection`
  - `TeamsSection`
  - `StandingsSection`
  - `TeamStatsSection`
  - `H2HSection`
  - `FormSection`
  - `AvailabilitySection`
  - `LineupsSection`
  - `OddsSection`
  - `ResearchSection`
  - `DerivedFeaturesSection`
  - `DataQualitySection`
- Any unexpected extra fields or mutations raise `pydantic.ValidationError` immediately.

---

## 13. Migration State
- Current Alembic head: `0010_m6_3_freshness_policy.py`.
- Schema chain 0001 -> 0010 verified:
  - `alembic upgrade head`
  - `alembic downgrade -1` (recreates 0009 constraint with `policy_fingerprint`)
  - `alembic upgrade head`
  - `alembic check` -> No new upgrade operations detected (0 schema drift).

---

## 14. Unit Tests
- `uv run pytest -q -m "not integration"`
- **357 passed, 96 deselected in 4.62s** (100% pass).

---

## 15. Integration Tests
- `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration`
- **96 passed, 357 deselected in 17.78s** (100% pass).

---

## 16. Full Pytest
- `uv run pytest -q`
- **453 passed in 20.15s** (100% pass).

---

## 17. Ruff / Format / Mypy
- `uv run ruff check .` -> All checks passed!
- `uv run ruff format --check .` -> 175 files already formatted.
- `uv run mypy src` -> Success: no issues found in 118 source files.

---

## 18. Alembic
- Migration status: Head at `0010`.
- Drift check: `alembic check` clean.

---

## 19. Docker Compose
- `docker compose config -q` -> Clean.
- `docker compose --profile telegram config -q` -> Clean.

---

## 20. GitHub Actions Result and Run ID
- **Run ID:** `36831445894`
- **Status:** `completed`
- **Conclusion:** `success`
- **Jobs:**
  - `lint / type / test (Python 3.12)`: SUCCESS (36s)
  - `integration tests (Postgres + Redis)`: SUCCESS (47s)
  - `docker compose config validation`: SUCCESS (4s)

---

## 21. Final Git Status
- Working tree: clean (`git status --short` is empty).

---

## 22. Confirmation
- `HEAD == origin/build/m6` (`5fb6c604617c7f93117e6d42d623a92082461981`).
- M6 is NOT merged into `main`.
- M7 is NOT started.
- All development remains strictly LOCAL ONLY.
