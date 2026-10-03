"""Bounded actual restart/failure/resource acceptance on an isolated local M10 stack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import uuid
from typing import Any

import httpx
from backup_restore import require_local_docker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    require_local_docker()
    if not re.fullmatch(r"sports-m10-[a-z0-9-]+", args.project):
        raise SystemExit("only explicitly isolated sports-m10-* projects may be restarted")
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+", args.base_url):
        raise SystemExit("loopback API required")
    compose = ["docker", "compose", "-p", args.project, "--env-file", args.env_file]

    def docker(*items: str) -> str:
        return subprocess.check_output([*compose, *items], stderr=subprocess.PIPE, text=True)

    client = httpx.Client(base_url=args.base_url, timeout=10)

    def get(path: str) -> Any:
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def wait_run(run_id: str) -> Any:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = get("/v1/predictions/" + run_id)
            if value["status"] in ("SUCCEEDED", "FAILED", "ABSTAINED"):
                assert value["status"] == "SUCCEEDED", value["status"]
                return value
            time.sleep(0.5)
        raise RuntimeError("bounded worker completion timeout")

    stored = get("/v1/predictions")[0]
    original = get("/v1/predictions/" + stored["id"])
    fixture_id = original["fixture_id"]
    payload = {
        "context_id": original["match_context_id"],
        "rerun": True,
        "rerun_key": str(uuid.uuid4()),
    }
    try:
        docker("stop", "sports-worker")
        queued = client.post(f"/v1/fixtures/{fixture_id}/analyze", json=payload)
        queued.raise_for_status()
        queued_data = queued.json()
        assert queued_data["status"] == "QUEUED"
        docker("restart", "sports-api", "sports-beat", "sports-worker")
        # API startup is finite; retries here are test polling, not external provider retries.
        for _ in range(30):
            try:
                if client.get("/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        completed = wait_run(queued_data["run_id"])
        repeated = client.post(f"/v1/fixtures/{fixture_id}/analyze", json=payload).json()
        assert repeated["run_id"] == queued_data["run_id"] and repeated["already_queued"]
        assert get("/v1/predictions/" + original["id"]) == original
        before = completed
        docker("stop", "sports-redis")
        assert client.get("/ready").status_code == 503
        assert get("/v1/predictions/" + before["id"]) == before
        docker("start", "sports-redis")
        time.sleep(2)
        assert client.get("/ready").status_code == 200
        docker("stop", "sports-postgres")
        assert client.get("/ready").status_code == 503
        failed_read = client.get("/v1/predictions/" + original["id"])
        assert failed_read.status_code == 500 and "Traceback" not in failed_read.text
        docker("start", "sports-postgres")
        for _ in range(30):
            if client.get("/ready").status_code == 200:
                break
            time.sleep(0.5)
        assert client.get("/ready").status_code == 200
        assert get("/v1/predictions/" + original["id"]) == original
        started = time.monotonic()
        batch = []
        for _ in range(12):
            payload["rerun_key"] = str(uuid.uuid4())
            response = client.post(f"/v1/fixtures/{fixture_id}/analyze", json=payload)
            response.raise_for_status()
            batch.append(response.json()["run_id"])
        for run_id in batch:
            assert len(wait_run(run_id)["probabilities"]) == 12
        elapsed = round(time.monotonic() - started, 2)
        ids = docker("ps", "-q").splitlines()
        stats = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], text=True
        )
        metrics = [json.loads(line) for line in stats.splitlines()]
        size = docker(
            "exec",
            "-T",
            "sports-postgres",
            "psql",
            "-X",
            "-U",
            "sports",
            "-d",
            "sports_intel_acceptance_test",
            "-At",
            "-c",
            "SELECT pg_database_size(current_database())",
        ).strip()
        memory = docker("exec", "-T", "sports-redis", "redis-cli", "INFO", "memory")
        redis_bytes = next(
            line.split(":")[1].strip()
            for line in memory.splitlines()
            if line.startswith("used_memory:")
        )
        print(
            json.dumps(
                {
                    "restart_recovery": "PASS",
                    "queued_prediction_id": queued_data["run_id"],
                    "postgresql_outage": "PASS",
                    "redis_outage": "PASS",
                    "old_prediction_unchanged": True,
                    "batch": {
                        "fixtures": 1,
                        "jobs": 12,
                        "probabilities": 144,
                        "seconds": elapsed,
                        "worker_concurrency": 2,
                        "kind": "synthetic local workload",
                    },
                    "containers": metrics,
                    "postgres_database_bytes": int(size),
                    "redis_used_memory_bytes": int(redis_bytes),
                    "recent_log_bytes": len(docker("logs", "--no-color", "--since", "5m").encode()),
                    "limits": (
                        "multi-day empirical operation and "
                        "interrupted unknown paid calls not proven"
                    ),
                },
                sort_keys=True,
            )
        )
    finally:
        # Restore availability even if an assertion fails. No volume deletion or data reset.
        docker(
            "start", "sports-postgres", "sports-redis", "sports-api", "sports-worker", "sports-beat"
        )
        client.close()


if __name__ == "__main__":
    main()
