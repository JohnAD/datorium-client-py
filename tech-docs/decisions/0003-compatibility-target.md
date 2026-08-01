# 0003. Compatibility target

## Status

Accepted

## Context

The Go client historically documented older DatoriumDB tags while the database repo advanced. Some server behaviors (replication `note`, read staleness, hint-free `wrongMachine`) need an explicit client target.

## Decision

Target DatoriumDB **v0.0.5** for this release line. Use the Go client as the ergonomic/API baseline, but prefer the current server contract when they differ. Surface replication notes as structured optional write-result fields. Make stale-read failover configurable.

## Consequences

Contract fixtures are copied from `datoriumdb/test/contract/golden` and versioned in-repo. Drift updates are a deliberate developer task documented in COMPATIBILITY.md.
