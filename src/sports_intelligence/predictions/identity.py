from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fingerprint(value: Any) -> str:
    return content_hash(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


@dataclass(frozen=True)
class PromptIdentity:
    name: str
    version: str
    content: str
    source_identity: str

    @property
    def hash(self) -> str:
        return content_hash(self.content)


def load_prompt(path: str = "prompts/predictor/1.0.0.txt") -> PromptIdentity:
    source = Path(path)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", source.stem):
        raise ValueError("prompt filename requires semantic version, e.g. 1.0.0.txt")
    content = source.read_text(encoding="utf-8")
    return PromptIdentity("predictor", source.stem, content, source.as_posix())


def prediction_identity(
    *,
    context_hash: str,
    prompt_hash: str,
    prompt_version: str,
    provider: str,
    model: str,
    config_hash: str,
    variant: str,
    role: str,
    phase: str,
    policy_hash: str,
) -> str:
    return fingerprint(
        {
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
            "config_hash": config_hash,
            "variant": variant,
            "role": role,
            "phase": phase,
            "policy_hash": policy_hash,
            "engine_version": "m7_v1",
        }
    )
