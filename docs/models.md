# Dataclasses and Pydantic models

Define ordinary Python classes for your documents, bind them to an existing server collection, then create, read, patch, and delete through a typed client—similar in spirit to a lightweight ORM. Collections themselves are defined by server administrators; this API only binds to what the server's catalog already exposes.

Both stdlib dataclasses and Pydantic v2 `BaseModel` classes are supported (Pydantic is required). The bind step returns a `CollectionClient` (or async equivalent). For the raw dictionary API, see [documents.md](documents.md).

## Binding to a Collection

Field **declaration order** in your model must match the Datorium schema’s child order. Wire names default to field names; override with aliases when they differ:

```python
from dataclasses import dataclass
from pydantic import BaseModel, Field
from datorium_client import Collection

class Todo(BaseModel):
    title: str
    status: str = Field(serialization_alias="status")

@dataclass
class TodoDC:
    title: str
    status: str  # optional: metadata={"wire": "status"}
```

```python
todos = Collection.of(Todo, "Todos", 0).bind(client)
```

| Piece | What to pass |
| --- | --- |
| `Collection.of(model_type, name, version)` | Your model class, catalog collection name, and schema version integer (marker becomes `{name}:{version}`). |
| `.bind(client)` | An established `Client`. Checks that the model shape matches the server schema before returning a `CollectionClient`. |

Binding compares names, order, nested kinds, arrays, requiredness, and nullability. Mismatches raise before any write is attempted.

---

## `create_doc(doc, doc_id=None, *, extra_fields=None) -> WriteResult`

Creates a document from a model instance. The client sets `$` from the collection marker and mints `operationId`.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `doc` | `T` | Model instance with application fields only (no `$` / `#` / `!`). Values must satisfy the bound schema. |
| `doc_id` | `str \| None` | Stable document id, or omit / `None` to mint a ULID. Empty string is rejected. |
| `extra_fields` | `Mapping[str, Any] \| None` | Optional non-schema fields to store on the document (use `OrderedDict` when order matters). Keys must not collide with model fields or meta keys (`$`, `#`, `!`, `operationId`). |

Returns `WriteResult` (`id`, `schema`, `version`, …). See [documents.md](documents.md).

```python
from collections import OrderedDict

wr = todos.create_doc(Todo(title="Buy milk", status="open"))
# or: todos.create_doc(Todo(...), doc_id="todo1")
wr = todos.create_doc(
    Todo(title="Buy milk", status="open"),
    extra_fields=OrderedDict([("source", "mobile"), ("priority", 1)]),
)
```

On read, those fields appear in `CollectionItem.extra_fields` when requested with `ReadOptions(extra_fields=True)`—not on the model.

---

## `get_doc(doc_id) -> CollectionItem[T]`

Reads a document and maps schema fields onto your model.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `doc_id` | `str` | Document id (from `WriteResult.id` or your own id). |

For read options, use `get_doc_opts(doc_id, opts)` with the same `ReadOptions` as raw `read` (`extra_fields`, `cache_summaries`; see [documents.md](documents.md)).

`CollectionItem` useful fields:

| Attribute | Meaning |
| --- | --- |
| `doc` | Mutable model instance (edit this, then patch) |
| `original_doc` | Snapshot as loaded |
| `meta` | `DocMeta(id, schema, version)` for concurrency |
| `extra_fields` / `cache_summaries` | Only when requested via `get_doc_opts` |
| `result` | Underlying `ReadResult` |

A missing document raises `AppError` with code `documentNotFound`. See [errors.md](errors.md).

```python
item = todos.get_doc(wr.id)
print(item.doc.title, item.meta.version)
```

---

## `patch_doc(patch) -> WriteResult`

Applies a typed `CollectionPatch` built from an item.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `patch` | `CollectionPatch[T]` | From `create_patch_from_changes(item)` or `create_patch(item, ops)`. Must come from the same bound collection client as the item. |

For snapshot-diff and explicit RFC 6902 builders, see [patches.md](patches.md).

```python
item = todos.get_doc(wr.id)
item.doc.status = "done"
todos.patch_doc(todos.create_patch_from_changes(item))
```

---

## `delete_doc(...) -> WriteResult`

Deletes a document. Two forms:

**From an item** (uses `meta.id` / `meta.version`):

| Parameter | Type | What to pass |
| --- | --- | --- |
| `item` | `CollectionItem[T]` | Item from `get_doc` / `get_doc_opts` on this bound client. |

**From id + version** (no prior read required if you already know both):

| Parameter | Type | What to pass |
| --- | --- | --- |
| `doc_id` | `str` | Document id. |
| `version` | `str` | Current document version (`#`). |

Stale version yields `versionMismatch`.

```python
item = todos.get_doc(wr.id)
todos.delete_doc(item)

# or, when id and version are already known:
todos.delete_doc(wr.id, wr.version)
```

---

## Extra fields

Non-schema fields returned by the server are kept on `CollectionItem.extra_fields` (an `OrderedDict` of ordinary Python values: `str`, `bool`, `Decimal`, nested ordered maps/lists, plus `Null` / `Void` sentinels). They are not merged into the model.
