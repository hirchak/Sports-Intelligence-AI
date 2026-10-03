"""Bounded heuristic Git/history and known-local-secret scan. Prints locations, never values.

This is a sanity check, not a complete vulnerability or entropy scanner.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def main() -> None:
    known = [
        str(value).encode()
        for key, value in dotenv_values(".env").items()
        if re.search(r"(?:API_KEY|BOT_TOKEN)$", key) and value and len(value) >= 12
    ]
    patterns = [
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}\b"),
    ]
    objects = git("rev-list", "--objects", "--all").splitlines()
    names = {line.split(b" ", 1)[0]: line.split(b" ", 1)[1] for line in objects if b" " in line}
    findings = []
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert process.stdin and process.stdout
    for oid, name in names.items():
        process.stdin.write(oid + b"\n")
        process.stdin.flush()
        header = process.stdout.readline().split()
        if len(header) < 3:
            raise RuntimeError("unexpected Git object response")
        body = process.stdout.read(int(header[2]))
        process.stdout.read(1)
        if header[1] == b"blob" and (
            any(secret in body for secret in known)
            or any(pattern.search(body) for pattern in patterns)
        ):
            findings.append(f"history {oid.decode()} {name.decode(errors='replace')}")
    process.stdin.close()
    process.wait()
    working = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    for filename in working:
        path = Path(filename.decode())
        if path.is_file():
            body = path.read_bytes()
            if any(secret in body for secret in known) or any(p.search(body) for p in patterns):
                findings.append(f"working tree {path}")
    if findings:
        raise SystemExit("secret sanity FAIL at: " + "; ".join(findings))
    for filename in (".env", "database.dump", "database.sql.gz", "database.backup"):
        if subprocess.run(["git", "check-ignore", "-q", filename]).returncode != 0:
            raise SystemExit("missing ignore rule for " + filename)
    print(
        f"PASS: {len(working)} working paths, {len(names)} history objects; "
        f"{len(known)} known-local credential fingerprints; heuristic limitations apply"
    )


if __name__ == "__main__":
    main()
