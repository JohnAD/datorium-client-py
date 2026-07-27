# 0009. wrongMachine retries use establishment only

## Status

Accepted

## Context

DatoriumDB currently emits `correctServer`, `baseURL`, and `configVersion` on `wrongMachine` refusals. Taking next-hop instructions from a machine that has already refused the request can create temporal routing loops. A bounce’s `configVersion` only reports what that server believes; the authoritative version comes from the establishment server.

## Decision

- On `wrongMachine`, always call `establish()` again.
- Recompute the next hop from the fresh establishment document.
- Ignore `correctServer` and `baseURL` on bounce envelopes (even while the server still sends them).
- Do not use bounce `configVersion` to decide whether to refresh.

See also `datoriumdb/tech-docs/TODO-REMOVE-WRONG-MACHINE-HINTS.md`.

## Consequences

Extra establishment fetches on every bounce. Safer routing under stale or misconfigured non-establishment members.
