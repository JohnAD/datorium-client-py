# 0007. Scope boundaries

## Status

Accepted

## Context

Several features exist around the smart-client surface: polling for eventual visibility, machine tokens, and `/sys/*` replication agent APIs.

## Decision

Out of scope for the first release:

- Public polling / wait helpers (data integrity is server-owned; apps may loop if they need visibility)
- Machine-token bootstrap and `/sys/*` replication endpoints
- Multi-document transactions (not offered by the server)

In scope for tests only: a JWT minting helper under test tooling, not the public runtime API.

## Consequences

Integration tests may mint tokens privately. Replication agents need a different client surface later if required.
