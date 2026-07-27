# 0008. Random SHARD_READ_MEMBER routing

## Status

Accepted

## Context

An earlier draft exposed `prefer_server` so callers could bias local routing toward one server. That API was confusing and not how this client should behave.

## Decision

- Remove `prefer_server` from `Config`.
- Document reads choose a `SHARD_READ_MEMBER` uniformly at random.
- Failover uses a shuffled permutation of the remaining read members.
- Do not use `PROXY_READ_MEMBER` for document reads.

## Consequences

Callers cannot pin reads to a specific server via client config. Load spreads across eligible read members; `wrongMachine` and stale-read policies still apply.
