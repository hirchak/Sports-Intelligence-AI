"""Redact credential-bearing keys/URLs and registered runtime secrets, including tracebacks."""

from __future__ import annotations

import os
import re
from typing import Any

_SENSITIVE = re.compile(
    r"(?:.*api.?key|(?:.*_)?token|(?:.*_)?password|(?:.*_)?secret|authorization|cookie)$", re.I
)
_PATTERNS = (
    (re.compile(r"(?i)([?&](?:api.?key|token|password|secret)=)[^&\s\"']+"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?:Bearer\s+)?[^\s,\"'}]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)((?:api.?key|token|password|secret)[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(://[^:/\s]+:)[^@\s]+(@)"), r"\1[REDACTED]\2"),
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b"), "[REDACTED]"),
)
_secrets: set[str] = set()


def register_secrets(values: dict[str, Any]) -> None:
    for key, value in values.items():
        if _SENSITIVE.search(key) and isinstance(value, str) and len(value) >= 8:
            _secrets.add(value)


def redact(value: str) -> str:
    for secret in sorted(_secrets, key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if _SENSITIVE.search(str(k)) else redact_payload(v)
            for k, v in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [redact_payload(v) for v in value]
    return redact(value) if isinstance(value, str) else value


register_secrets(dict(os.environ))
