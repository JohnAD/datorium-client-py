# 0009. wrongMachine retries use establishment only

## Status

Accepted

## Context

Older DatoriumDB releases emitted `correctServer`, `baseURL`, and `shardSlot` on `wrongMachine` refusals. Taking next-hop instructions from a machine that has already refused the request can create temporal routing loops. As of DatoriumDB v0.0.5, those routing hints are removed. A bounce may still include `configVersion`, which only reports what that refusing server believes; the authoritative version comes from the establishment server.

## Decision

- On `wrongMachine`, always call `establish()` again.
- Recompute the next hop from the fresh establishment document.
- Ignore `correctServer`, `baseURL`, and `shardSlot` on bounce envelopes when present (legacy parse-only).
- Do not use bounce `configVersion` to decide whether to refresh; treat it as diagnostic only.

## Consequences

Extra establishment fetches on every bounce. Safer routing under stale or misconfigured non-establishment members. Contract goldens match the hint-free envelope shape.
