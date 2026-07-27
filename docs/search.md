# Search

Searches are **precompiled** on the server. The client sends variables for a named search; it does not accept arbitrary query languages.

```python
from datorium_client import searchpath

segments = searchpath.equals_string_segments("open")
result = client.search(
    "Todos",
    "byStatus",
    {"status": "open"},
    path_segments=segments,
)
print(result.matches)
```

Providing `path_segments` lets the client route to the correct search shard immediately. Omitting them may trigger a `wrongMachine` bounce, which the client handles automatically.

Search indexes can lag briefly after writes. See [eventual-visibility.md](eventual-visibility.md).
