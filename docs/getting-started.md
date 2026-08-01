# Getting started

## Install

```bash
pip install datorium-client
```

Requires Python 3.11+ and a reachable DatoriumDB establishment server.

Generic (dictionary) access works for quick scripts and tooling. Prefer **typed** access with dataclasses or Pydantic models when you can: it preserves field order, checks schema shape at bind time, and is safer for application code.

## Connect

```python
from datorium_client import Client, Config

client = Client(
    Config(
        establishment_url="http://localhost:8080",
        token="YOUR_BEARER_TOKEN",
    )
)
```

Prefer a context manager so the HTTP client is closed cleanly:

```python
with Client(Config(establishment_url="...", token="...")) as client:
    ...
```

The client fetches establishment automatically on the first routed operation or typed bind. You do not need to call `establish()` yourself.

## First document

Use an ordered mapping so field order is stable on the wire:

```python
from collections import OrderedDict

result = client.create(
    "Todos",  # collection name
    "",       # empty → client mints a ULID
    OrderedDict(
        [
            ("$", "Todos:0"),  # schema marker: Collection:version
            ("title", "Buy milk"),
            ("status", "open"),
        ]
    ),
)
print(result.id, result.version)
```

## Typed models (recommended)

```python
from pydantic import BaseModel
from datorium_client import Collection

class Todo(BaseModel):
    title: str
    status: str

todos = Collection.of(Todo, "Todos", 0).bind(client)  # verifies Todo matches server schema
todos.create_doc(Todo(title="Buy milk", status="open"))
```

Next: [client.md](client.md), [models.md](models.md).
