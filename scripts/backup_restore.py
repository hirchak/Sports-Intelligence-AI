"""Local PostgreSQL native backup and non-destructive temporary restore verification.

Only a local Docker Unix-socket context is permitted. The source must be quiescent.
No restore-to-existing-db operation is offered. Archives live in a private temp directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def require_local_docker() -> None:
    if os.environ.get("DOCKER_HOST") and not os.environ["DOCKER_HOST"].startswith("unix://"):
        raise RuntimeError("local Docker Unix socket required")
    context = json.loads(run(["docker", "context", "inspect"], text=True).stdout)[0]
    if not context["Endpoints"]["docker"]["Host"].startswith("unix://"):
        raise RuntimeError("remote Docker contexts are forbidden")


def inventory(prefix: list[str], database: str, user: str) -> dict[str, Any]:
    def sql(query: str) -> str:
        return run(
            [
                *prefix,
                "psql",
                "-X",
                "-U",
                user,
                "-d",
                database,
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                query,
            ],
            text=True,
        ).stdout.strip()

    tables = sql(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ).splitlines()
    result: dict[str, Any] = {}
    for table in tables:
        if not re.fullmatch(r"[a-z_0-9]+", table):
            raise RuntimeError("unexpected table name")
        # Hash every row, including schema version and identities.
        result[table] = (
            sql(f'''SELECT count(*) || ':' || md5(coalesce(string_agg(r, E'\\n' ORDER BY r), ''))
            FROM (SELECT row_to_json(t)::text r FROM "{table}" t) rows''')
        )
    if "match_contexts" in tables:
        rows = json.loads(
            sql(
                "SELECT coalesce(json_agg(t), '[]') FROM "
                "(SELECT id, context_hash, context_jsonb FROM match_contexts) t"
            )
        )
        for row in rows:
            canonical = json.dumps(
                row["context_jsonb"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                default=str,
            )
            if hashlib.sha256(canonical.encode()).hexdigest() != row["context_hash"]:
                raise RuntimeError("stored MatchContext hash mismatch")
        result["verified_context_hashes"] = len(rows)
    return result


def verify_backup(
    project: str, database: str, user: str, env_file: str | None = None
) -> dict[str, Any]:
    require_local_docker()
    for name in (project, database, user):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", name):
            raise ValueError("invalid local identifier")
    compose = ["docker", "compose", "-p", project]
    if env_file:
        compose += ["--env-file", env_file]
    prefix = [*compose, "exec", "-T", "sports-postgres"]
    restored = "sports_restore_" + uuid.uuid4().hex[:12] + "_test"
    before = inventory(prefix, database, user)
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="sports-backup-") as directory:
            Path(directory).chmod(0o700)
            archive = Path(directory) / "database.dump"
            with archive.open("wb") as output:
                archive.chmod(0o600)
                subprocess.run(
                    [
                        *prefix,
                        "pg_dump",
                        "-U",
                        user,
                        "-d",
                        database,
                        "-Fc",
                        "--no-owner",
                        "--no-acl",
                    ],
                    stdout=output,
                    stderr=subprocess.PIPE,
                    check=True,
                )
            if inventory(prefix, database, user) != before:
                raise RuntimeError("source changed during backup; quiesce writers and retry")
            run([*prefix, "createdb", "-U", user, "-O", user, "-T", "template0", restored])
            created = True
            with archive.open("rb") as data:
                run(
                    [
                        *prefix,
                        "pg_restore",
                        "-U",
                        user,
                        "-d",
                        restored,
                        "--exit-on-error",
                        "--single-transaction",
                        "--no-owner",
                        "--no-acl",
                    ],
                    stdin=data,
                )
            after = inventory(prefix, restored, user)
            if before != after:
                raise RuntimeError("restore inventory mismatch")
            return {
                "status": "PASS",
                "archive_bytes": archive.stat().st_size,
                "tables": before,
                "restore_database": restored,
                "cleanup": "temporary DB/archive removed on exit",
            }
    finally:
        if created:
            run([*prefix, "dropdb", "-U", user, restored])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", default="sports")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                verify_backup(args.project, args.database, args.user, args.env_file), sort_keys=True
            )
        )
    except subprocess.CalledProcessError as exc:
        # Native diagnostics may contain credentials: never echo command/output/traceback.
        raise SystemExit(f"native backup/restore failed (exit {exc.returncode})") from None


if __name__ == "__main__":
    main()
