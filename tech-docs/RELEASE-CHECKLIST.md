# Release checklist

1. Update `CHANGELOG.md` and package version in `pyproject.toml` / `__init__.py`.
2. `uv run ruff check src tests`
3. `uv run mypy src/datorium_client`
4. `uv run pytest tests/unit tests/contract tests/integration/todo`
5. Optional: Docker integration against DatoriumDB v0.0.5 (`./start_integration_test.sh`).
6. `uv build` and verify the wheel imports.
7. Tag and publish to PyPI.
