# datorium-client

Pure Python smart client for [DatoriumDB](https://github.com/JohnAD/datoriumdb).

Targets DatoriumDB **v0.0.4** (`/datoriumdb/v1`).

## Install

```bash
pip install datorium-client
# or
uv add datorium-client
```

Requires Python 3.11+.

## Quick start

```python
from datorium_client import Client, Config

with Client(Config(establishment_url="http://localhost:8080", token=TOKEN)) as client:
    client.establish()
    client.create("Todos", "", {"$": "Todos:0", "title": "Buy milk", "status": "open"})
```

See [docs/](docs/) for user guides. Developer notes and ADRs live in [tech-docs/](tech-docs/).

## Development

```bash
uv sync --extra dev
uv run pytest tests/unit tests/contract
uv run ruff check src tests
uv run mypy src/datorium_client
```

Optional two-shard Compose integration (requires Docker and a sibling
[`datoriumdb`](https://github.com/JohnAD/datoriumdb) checkout):

```bash
./start_integration_test.sh
```

See [tech-docs/TESTING.md](tech-docs/TESTING.md).

## License

MIT
