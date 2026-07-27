# Contributing

1. Read [tech-docs/](tech-docs/) and the ADR index under [tech-docs/decisions/](tech-docs/decisions/).
2. Keep user docs in [`docs/`](docs/) free of protocol internals.
3. Prefer adding decisions as ADRs when changing architecture.

```bash
uv sync --extra dev
uv run ruff check src tests
uv run mypy src/datorium_client
uv run pytest tests/unit tests/contract
```

Integration tests require Docker and a sibling `datoriumdb` checkout:

```bash
./start_integration_test.sh
```

See [tech-docs/TESTING.md](tech-docs/TESTING.md).
