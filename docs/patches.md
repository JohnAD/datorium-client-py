# Patches

DatoriumDB uses optimistic concurrency: every patch or delete includes the document version (`#`). If the version is stale, the server returns `versionMismatch`.

## Snapshot diff (typed)

```python
item = todos.get_doc(doc_id)
item.doc.status = "done"
patch = todos.create_patch_from_changes(item)
todos.patch_doc(patch)
```

## Explicit patch builder (typed)

```python
from datorium_client._patch import parse_patch  # prefer public helpers as they stabilize

patch = todos.create_patch(
    item,
    [{"op": "replace", "path": "/status", "value": "done"}],
)
todos.patch_doc(patch)
```

## Raw patch with version retry

```python
def build(read):
    version = read.sot["#"]
    return {
        "$": "Todos:0",
        "#": version,
        "RFC6902": [{"op": "replace", "path": "/status", "value": "done"}],
    }

client.patch_with_version_retry("Todos", doc_id, build)
```
