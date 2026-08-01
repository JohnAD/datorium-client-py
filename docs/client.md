# Client configuration

## Synchronous and asynchronous APIs

`Client` and `AsyncClient` expose the same operations. Use sync for scripts and simple services; use async when your application is already asyncio-based.

```python
from datorium_client import AsyncClient, Config

async with AsyncClient(Config(establishment_url="...", token="...")) as client:
    await client.health()
```

## Config fields

| Field | Purpose |
|-------|---------|
| `establishment_url` | Base URL of the establishment server (required) |
| `token` / `token_source` | Bearer token (one required) |
| `collections` | Optional `[(name, schema_version), ...]` catalog check applied on the first automatic establish |
| `base_url_rewrite` | Map Docker-internal URLs or server names to host-reachable URLs |
| `wrong_machine_retries` | Bound for routing bounce loops (default 3) |
| `transport_retries` | Retries on transport failures (default 0) |
| `create_ambiguous_verify_delay` | Seconds to wait before verifying a create after a transport error (default 3; negative disables) |
| `stale_read_policy` | How to handle `readMemberStale` / `documentStale` on reads (default `failover`; also `surface`, `prefer_sot`) |
| `user_agent` | HTTP User-Agent |
| `timeout` | httpx timeout seconds (default 30) |

## Stale read policy

DatoriumDB read members can refuse a read with application errors:

- `readMemberStale` — the read member has lost contact with the shard’s SOT long enough that it will not serve reads
- `documentStale` — this document has a pending replicated write that has not been applied locally yet

| Policy | Behavior |
|--------|----------|
| `failover` (**default**) | Try other `SHARD_READ_MEMBER` servers for that shard; if all fail the same way, raise the last error |
| `surface` | Raise the first stale error immediately |
| `prefer_sot` | After read-member stale failures, try the shard’s `SHARD_SOT_MEMBER` once |

This is independent of `wrongMachine` handling (which always re-fetches establishment). Stale policy never claims the client can make a stale replica “correct”; it only chooses where to ask next.

## Establishment

Establishment is automatic: the first routed operation, `bind`, or `await bind_async` fetches and caches the establishment document. Set `Config.collections` (or call `establish(...)` with `(collection, schema_version)` pairs) when you want an early catalog check; call `establish()` with no args to force a refresh.

On `wrongMachine`, the client **always** re-fetches establishment from the establishment server before choosing another hop. A `configVersion` on a bounce is only diagnostic (what that refusing server thinks); it is not authoritative.

## Routing

- Writes go to the shard’s `SHARD_SOT_MEMBER`.
- Document reads go to a randomly chosen `SHARD_READ_MEMBER` for that shard (never `PROXY_READ_MEMBER`).
- Searches with known path segments also choose a random `SHARD_READ_MEMBER` when available.
- Bounce fields such as `correctServer` and `baseURL` are ignored; next hops come only from establishment.
