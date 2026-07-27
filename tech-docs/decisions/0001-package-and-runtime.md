# 0001. Package name, Python floor, runtime dependencies

## Status

Accepted

## Context

Greenfield Python client needs a PyPI name, import path, minimum language version, and packaging baseline.

## Decision

- PyPI project: `datorium-client`
- Import package: `datorium_client`
- Python: 3.11+
- Packaging: uv + hatchling
- Lint/type/test: Ruff, mypy strict, pytest
- Runtime dependencies: `httpx`, `pydantic` (v2 required)
- ULID generation and Datorium JSON semantics are implemented in pure Python

## Consequences

Applications must use Python 3.11+. Pydantic is a hard dependency even for dataclass-only callers (via `TypeAdapter`).
