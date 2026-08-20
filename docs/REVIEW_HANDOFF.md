# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M0 + M0.1 fixes — awaiting final review  
**Review target commit:** (M0.1 commit hash on `build/m0` — see Git section)  
**Review target tag:** `v0.1-m0` (moved to the final M0 state)  
**Previous accepted commit:** `8723a91` (spec pack on `main`)  
**Previous review:** M0 → PASS WITH FIXES; fixes implemented in M0.1

---

# What changed since the last review

M0.1 fixes (all items from the PASS WITH FIXES verdict):

1. **`.env` loading through `Settings` fixed**
   - `env_ignore_empty=True` — empty values behave as unset;
   - `extra="ignore"` — Compose-only `POSTGRES_USER/PASSWORD/DB` in the shared
     `.env` no longer break startup;
   - `TELEGRAM_ALLOWED_USER_IDS` uses `NoDecode` + explicit comma-separated
     before-validator (empty → `[]`, `123,456` → `[123,456]`);
   - declared settings keep full type validation (bad `DEFAULT_MIN_ODDS` fails).
   - Policy documented in ADR-0004 (updated).
2. **Dotenv regression tests** — 7 new cases reading real dotenv files
   (`tests/unit/test_config_dotenv.py`).
3. **README clone instructions** fixed (`git clone … sports-intelligence`
   instead of broken `cd -`); same in `docs/LOCAL_DEVELOPMENT.md`.
4. **Technical debt recorded** in `docs/IMPLEMENTATION_STATUS.md`:
   - M1: `/ready` must use shared DB engine/Redis client from FastAPI
     lifespan (currently created per request);
   - M2: provider interfaces must move from `dict[str, Any]` to normalized
     internal DTO/Pydantic schemas before the first real sports adapter.

---

# What should the reviewer verify?

- `.env.example` loads through `Settings(_env_file=…)` without errors;
- comma/empty `TELEGRAM_ALLOWED_USER_IDS` parsing via real dotenv;
- Compose-only variables tolerated while declared-field types still fail fast;
- dotenv tests genuinely exercise the file path (not only kwargs);
- clone instructions in README and LOCAL_DEVELOPMENT are correct;
- technical debt entries are clear and scheduled;
- milestone tag `v0.1-m0` points at the final M0.1 commit.

---

# Commands claimed as passing

Run these on branch `build/m0`:

```bash
uv sync --frozen --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
docker compose config -q
docker compose up -d --build
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
docker compose run --rm sports-api alembic upgrade head
```

Expected: 24 tests passed; ruff/mypy clean; services healthy; 200s;
alembic exit 0.

Reviewer must not assume tests passed based on status text alone.

---

# Known limitations

- No database models/migrations yet (M1).
- No Celery/aiogram (M1/M3).
- Provider/LLM adapters are interfaces only; nothing claims live integration.
- starlette pinned `<1.0` (testclient httpx deprecation) — revisit at next
  dependency bump.
- `extra="ignore"` reduces unknown-variable typo detection; mitigated by
  dotenv regression tests.
- Scheduled technical debt: M1 lifespan-shared engine/client; M2 normalized
  provider DTOs (see IMPLEMENTATION_STATUS).

---

# Files of highest relevance

- `src/sports_intelligence/core/config.py`
- `tests/unit/test_config_dotenv.py`
- `docs/adr/0004-runtime-modes-and-config-validation.md`
- `.env.example`, `README.md`
- `docs/IMPLEMENTATION_STATUS.md` (technical debt section)
- Git diff `6c8a193..<M0.1 commit>`

---

# Questions for reviewer

1. Are all PASS WITH FIXES items resolved without new shortcuts?
2. Do the dotenv tests prove the documented behavior on the real code path?
3. Is the validation policy (extra="ignore") acceptable given the shared
   `.env` constraint?
4. Are the recorded M1/M2 technical debt items sufficient to prevent
   architecture drift?
5. Is the next milestone safe to start?

---

# Reviewer output expected

```text
VERDICT: PASS / PASS WITH FIXES / FAIL

P0 critical
P1 high
P2 medium
P3 low

Tests independently run:
...

Required fixes before next milestone:
...

Safe to begin next milestone:
YES / NO
```
