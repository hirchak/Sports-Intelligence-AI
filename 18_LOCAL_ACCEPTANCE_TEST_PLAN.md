# Local Acceptance Test Plan
## What Must Work Before Hetzner Deployment

This document is a practical gate.

Do not deploy because "the code looks done."

---

# 1. Clean bootstrap

On a clean environment:

- clone repository;
- create `.env`;
- start Docker;
- run migrations;
- seed leagues.

Expected:
- no manual DB hacking;
- no missing undocumented files.

---

# 2. Mock end-to-end

With no real keys:

```text
fixture discovery
→ data collectors
→ data quality
→ features
→ MatchContext
→ mock LLM prediction
→ ranking
→ Telegram/test transport
→ final result injection
→ settlement
→ evaluation
```

Expected:
- deterministic;
- CI-compatible.

---

# 3. Real sports provider smoke test

Use one fixture.

Verify:

- fixture found;
- raw payload stored;
- normalized fixture stored;
- quota headers captured if provider supplies them;
- no duplicate external calls on immediate repeat when cache is fresh.

---

# 4. Batch test

Use several fixtures.

Verify:

- provider adapter batches IDs where supported;
- no N+1 standings calls;
- same team/league snapshots reused;
- API request ledger reflects cache hits.

---

# 5. Prediction reproducibility

For one prediction record:

Verify stored:

- fixture;
- MatchContext hash;
- `as_of`;
- feature version;
- prompt hash/version;
- model provider/model;
- odds snapshot;
- quality report.

Run identical input/config again.

Expected:
- cached/reproducible behavior according to policy.

---

# 6. No-leakage test

Create:

- morning context timestamp;
- later lineup;
- later odds;
- final result.

Replay morning prediction.

Expected:
- later rows excluded.

---

# 7. Telegram test

Verify:

- unauthorized user rejected;
- `/today`;
- fixture detail;
- manual analyze;
- duplicate tap;
- prediction display;
- stats;
- health;
- pagination;
- safe error message.

---

# 8. Provider failure test

Simulate:

- timeout;
- 429;
- 500;
- bad JSON;
- invalid auth.

Expected:
- correct retry classification;
- no tight retry loop;
- quota state updated where relevant;
- user gets safe status;
- job remains auditable.

---

# 9. LLM failure test

Simulate:

- timeout;
- malformed JSON;
- probabilities >1;
- 1X2 sum invalid;
- provider unavailable.

Expected:
- repair once;
- fail safely if still invalid;
- no malformed forecast published.

---

# 10. Settlement tests

Fixture outcomes:

```text
0-0
1-0
1-1
2-0
2-1
postponed
cancelled
extra time where competition rules matter
```

Verify all supported markets.

Settlement is deterministic.

---

# 11. Evaluation tests

Use known synthetic probabilities/results.

Verify:

- Brier;
- log loss;
- calibration buckets;
- sample sizes;
- coverage;
- segment filters.

---

# 12. Quota degradation test

Fake remaining quota levels.

Verify:

- optional tasks pause first;
- critical result settlement remains allowed;
- Telegram/admin reports degraded mode.

---

# 13. Restart test

During queued work:

- restart worker;
- restart bot;
- restart API.

Expected:
- DB state survives;
- retries do not duplicate completed prediction;
- bot is stateless relative to core work.

---

# 14. Database backup/restore

- create `pg_dump`;
- create clean temporary DB;
- restore;
- compare key row counts;
- verify one context hash/prediction.

---

# 15. Resource test

Run real local stack for several hours / representative batch.

Record:

- CPU;
- RAM;
- DB size;
- Redis;
- worker concurrency;
- log volume.

Use this evidence for Hetzner sizing.

---

# 16. Deployment gate

All must be true:

- [ ] full tests green
- [ ] local E2E green
- [ ] live provider smoke test green
- [ ] Telegram green
- [ ] leakage tests green
- [ ] quota controls green
- [ ] backup/restore green
- [ ] secret scan green
- [ ] independent audit PASS or PASS WITH ACCEPTED ISSUES
- [ ] Git tagged known-good version
