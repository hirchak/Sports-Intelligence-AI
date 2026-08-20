# ADR-0001: uv as Python package manager with committed lockfile

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M0

## Context

Master spec §4 requires "uv or another lockfile-based Python package manager.
Commit the lockfile." The project must be reproducible from a clean machine.

## Decision

Use `uv` with `pyproject.toml` + `uv.lock`. The lockfile is committed to Git.
CI installs with `uv sync --frozen` and the Docker image installs with
`uv sync --frozen --no-dev`, so the tested dependency set is identical
everywhere.

## Alternatives

- pip + pip-tools (weaker resolution, slower);
- Poetry (valid, but uv is faster and already prescribed by the spec pack).

## Consequences

- Deterministic environments locally, in CI and in containers.
- `uv.lock` must be regenerated (`make lock`) whenever dependencies change.

## Rollback/Migration

Switching to another lockfile-based manager only requires replacing
`pyproject.toml` build metadata and the lockfile; source layout stays valid.
