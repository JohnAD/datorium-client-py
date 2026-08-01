# Documents

Raw dictionary API on `Client` / `AsyncClient`. Prefer typed collections for application code ([models.md](models.md)). Field order in mappings is preserved on write. Reads return an `OrderedDict` with ordinary Python values: numbers as `Decimal`, JSON `null` as `Null`, and absent paths as `Void`. For generic updates, see [patches.md](patches.md) (raw patch with version retry).

Meta keys used in document payloads:

| Key | Meaning |
| --- | --- |
| `$` | Schema marker: `{CollectionName}:{version}` (for example `Todos:0`) |
| `#` | Document version string (optimistic concurrency; required on delete/patch) |
| `!` | Document id when present inside SOT (usually matches the command target id) |
| `operationId` | Client-supplied idempotency id; if omitted, the client mints one |

---

## `create(collection, doc_id, content) -> WriteResult`

Creates a new document on the shard’s source of truth.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `collection` | `str` | Collection name from the server catalog (for example `"Todos"`). |
| `doc_id` | `str` | Stable document id. Pass `""` to let the client mint a ULID. Prefer an explicit id when your app already has one. |
| `content` | `dict[str, Any]` | Document body. **Must** include `$` with the schema marker. Include application fields in schema order when possible (`OrderedDict` recommended). Do **not** set `#` on create (the server assigns versions). `operationId` is optional. |

Returns `WriteResult` (`id`, `schema`, `version`, `operation_id`, optional `note`). On success, use `result.id` / `result.version` for later reads and deletes.

```python
from collections import OrderedDict

wr = client.create(
    "Todos",
    "",  # client-minted ULID
    OrderedDict(
        [
            ("$", "Todos:0"),
            ("title", "Buy milk"),
            ("status", "open"),
        ]
    ),
)
print(wr.id, wr.version)
```

Application errors include `documentExists` if the id is already taken. See [errors.md](errors.md).

---

## `read(collection, doc_id, opts=None) -> ReadResult`

Reads the current source-of-truth document (via a randomly chosen read member; see [client.md](client.md)).

| Parameter | Type | What to pass |
| --- | --- | --- |
| `collection` | `str` | Same collection name used at create. |
| `doc_id` | `str` | Exact document id (from `WriteResult.id`, a prior `ReadResult.id` / `sot["!"]`, or your own id). |
| `opts` | `ReadOptions \| None` | Optional. Defaults to neither extras nor cache summaries. |

`ReadOptions`:

| Field | Default | Effect |
| --- | --- | --- |
| `extra_fields` | `False` | When `True`, non-schema fields are returned on `ReadResult.extra_fields`. |
| `cache_summaries` | `False` | When `True`, cached-ref summaries are returned on `ReadResult.cache_summaries`. |

`ReadResult` useful fields:

| Attribute | Meaning |
| --- | --- |
| `collection` / `id` | Echo of the target |
| `sot` | Document as `OrderedDict`, or `None` if absent from the envelope |
| `extra_fields` | Only when requested |
| `cache_summaries` | Only when requested |

A missing document raises `AppError` with code `documentNotFound` (HTTP 200 envelope), not HTTP 404.

```python
from datorium_client import ReadOptions

read = client.read("Todos", wr.id)
assert read.sot is not None
title = read.sot["title"]
version = read.sot["#"]

read = client.read(
    "Todos",
    wr.id,
    ReadOptions(extra_fields=True, cache_summaries=True),
)
```

---

## `patch(collection, doc_id, detail) -> WriteResult`

Applies an RFC 6902 patch to an existing document.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `collection` | `str` | Collection name. |
| `doc_id` | `str` | Document id to update. |
| `detail` | `dict[str, Any]` | **Must** include `$`, `#` (current version), and `RFC6902` (list of patch ops). `operationId` is optional (minted if omitted). |

For examples, version-mismatch retry (`patch_with_version_retry`), and typed patch helpers, see [patches.md](patches.md).

---

## `delete(collection, doc_id, detail) -> WriteResult`

Deletes a document. Requires the current version for optimistic concurrency.

| Parameter | Type | What to pass |
| --- | --- | --- |
| `collection` | `str` | Collection name. |
| `doc_id` | `str` | Document id to delete. |
| `detail` | `dict[str, Any]` | **Must** include `$` (schema marker) and `#` (current version from a recent read or write). `operationId` is optional (minted if omitted). |

If `#` is stale, the server returns `versionMismatch`. Re-read and retry with the new version, or use typed `delete_doc` after a fresh `get_doc`.

```python
read = client.read("Todos", wr.id)
client.delete(
    "Todos",
    wr.id,
    {
        "$": "Todos:0",           # or read.sot["$"]
        "#": read.sot["#"],       # required current version
    },
)
```

---

## Write results

Successful creates, patches, and deletes return a `WriteResult`:

| Attribute | Meaning |
| --- | --- |
| `id` | Document id |
| `schema` | Schema marker (`$`) |
| `version` | Version after the write (`#`, or `versions.after` on patch) |
| `version_before` | Previous version on patch (`versions.before`); empty for create/delete |
| `operation_id` | Operation id used for the write |
| `note` | Optional replication note when some members have not acknowledged yet |

A `note` does **not** mean the source-of-truth write failed. See [eventual-visibility.md](eventual-visibility.md).

---

## Typed collections

For `create_doc` / `get_doc` / `delete_doc`, see [models.md](models.md). Updates use patches: [patches.md](patches.md).
