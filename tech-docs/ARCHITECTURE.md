# Architecture

## Package layout

```
src/datorium_client/
  client.py / async_client.py   # public transports
  collection.py                 # typed collections
  envelope.py / errors.py       # result channel
  establishment.py / routing.py
  shard.py / searchpath.py / refs.py
  crud.py / command.py / ids.py
  schema_compat.py
  _json/ _schema/ _patch/       # internal ojson-compatible core
```

## Sync / async split

Protocol decoding, command construction, routing decisions, and establishment parsing are sync-agnostic. `Client` and `AsyncClient` own HTTP I/O and sleep/retry timing only.

## Concurrency

`EstablishmentCache` uses an `RLock`. After construction, clients are safe for concurrent use across threads (`Client`) or tasks (`AsyncClient`), provided the underlying httpx client is used according to httpx rules.

## Routing

- Writes → `SHARD_SOT_MEMBER` for the document slot.
- Document reads → a randomly chosen `SHARD_READ_MEMBER` (never `PROXY_READ_MEMBER`).
- Search (with path segments) → a randomly chosen `SHARD_READ_MEMBER` when present; otherwise SOT.
- There is no client-side preferred-server override.
- On `wrongMachine`, always re-fetch establishment; never follow bounce `correctServer` / `baseURL`. Bounce `configVersion` is diagnostic only.

## Integrity boundary

DatoriumDB owns durability and integrity. Client retries only address transport ambiguity, routing, and optimistic concurrency helpers. See ADR 0006 and 0007.
