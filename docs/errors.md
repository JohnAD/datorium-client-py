# Errors

DatoriumDB separates **HTTP transport** from **application outcomes**.

## Application channel (HTTP 200)

Logical and business results are returned as JSON envelopes with HTTP status 200:

- `ok: true` → success
- `ok: false` → `AppError` (for example `documentNotFound`, `versionMismatch`, `wrongMachine`)

A missing document on read is **not** an HTTP 404. It is HTTP 200 with `ok: false` and code `documentNotFound`.

```python
from datorium_client import AppError, is_app_code, CODE_DOCUMENT_NOT_FOUND

try:
    client.read("Todos", "missing")
except AppError as err:
    if is_app_code(err, CODE_DOCUMENT_NOT_FOUND):
        print("no such document")
```

## Transport errors (non-2xx)

HTTP 404, 502, connection failures, and unreadable bodies raise `TransportError`. These usually mean the client used the wrong URL, the server is down, or a proxy failed—not that a document is missing.

## Retries

The client may retry `wrongMachine` routing, optional transport failures, create verification after ambiguous transport errors, and one version-mismatch rebuild for `patch_with_version_retry`. Retries do not replace server-side integrity checks.
