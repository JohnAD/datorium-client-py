# 0003. Compatibility target

## Status

Accepted

## Context

The Go client documents DatoriumDB v0.0.2 while the database repo has advanced (v0.0.4). Some server behaviors (replication `note`, read staleness) are underrepresented in the Go client.

## Decision

Target DatoriumDB **v0.0.4 only** for the first release. Use the Go client as the ergonomic/API baseline, but prefer the current server contract when they differ. Surface replication notes as structured optional write-result fields. Make stale-read failover configurable.

## Consequences

Contract fixtures are copied from `datoriumdb/test/contract/golden` and versioned in-repo. Drift updates are a deliberate developer task documented in COMPATIBILITY.md.
