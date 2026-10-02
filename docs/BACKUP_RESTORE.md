# Native local backup and restore

LOCAL DEVELOPMENT ONLY. No remote cron, copying, server connection or deployment is configured.
Backups contain private runtime evidence and must never enter Git; .dump/.sql/.sql.gz/.backup/backups are ignored.

## Tested verification command

Quiesce writes on the selected local source database, then:

```bash
uv run python scripts/backup_restore.py --project sports-intel --database sports_intel --user sports
# Alternate keyless env/project:
uv run python scripts/backup_restore.py --project sports-m10-check --database sports_intel_acceptance_test --env-file .env
```

The script refuses remote Docker contexts and unsafe identifiers, uses `pg_dump -Fc --no-owner --no-acl`,
a mode0700 temporary directory and mode0600 archive, creates a unique clean *_test database using template0,
and runs `pg_restore --exit-on-error --single-transaction`. It never restores over an existing database.
It compares source before/after dump (refuses concurrent-write drift), schema-version/table inventories,
every table row count and stable full-row fingerprint, and recomputes stored MatchContext SHA256 identities.
Prediction/result/evaluation/experiment/proposal rows participate in those fingerprints. Finally it drops only
the generated temporary restore DB and removes its temp archive, including failure paths.

Run it during the complete E2E with M10_BACKUP_PROJECT/M10_BACKUP_DATABASE (LOCAL_DEVELOPMENT); that
population has context, prediction, result, three evaluations, experiment, comparison and proposal records.
Evidence/report contains hashes/counts only, never DB rows/credentials. The backup test needs local Docker
and is intentionally separate from keyless GitHub unit/integration jobs; CI still tests all migrations.

## Retained backup concept for future approved operations

MVP: nightly native compressed pg_dump, retention configurable (e.g. seven daily), restricted encrypted/
protected location with access limited to the operator, consistent naming without secrets, off-machine
copy when separately approved. Use an atomic completion marker/checksum and alert on failures; retain
only successful backups. Do not delete referenced evidence based on a retention assumption.
No remote automation is installed by M10.

Example local manual archive (operator-chosen private directory, never a repo path):

```bash
umask 077
docker compose exec -T sports-postgres pg_dump -U sports -d sports_intel -Fc --no-owner --no-acl > /private/path/database.dump
```

Create/verify a clean destination with matching Postgres major/tool versions. Restore a trusted archive
with pg_restore, check Alembic head, counts, context/prompt/model/prediction identities and evaluations;
perform an isolated health/E2E check before any future switch. A single DB dump excludes cluster roles and
external secret/config files: recreate roles and approved secrets separately. Never copy Docker volume trees.

Sources: [PostgreSQL16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).
