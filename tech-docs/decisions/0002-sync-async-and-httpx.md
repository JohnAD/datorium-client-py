# 0002. Dual sync/async APIs over httpx

## Status

Accepted

## Context

The Go client is synchronous. Python ecosystems commonly need both sync and async.

## Decision

Ship matching `Client` and `AsyncClient` APIs over `httpx.Client` / `httpx.AsyncClient`. Shared protocol logic (envelope decode, routing decisions, command construction) lives in sync-agnostic helpers. Injectable transports support unit tests without network I/O.

## Consequences

Public method surfaces must stay in parity. Contract tests parametrize both clients where practical.
