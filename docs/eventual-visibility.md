# Eventual visibility

DatoriumDB maintains data integrity. The client does not reconcile or “heal” data.

Some derived views update asynchronously after a successful write:

- Precompiled search indexes
- Cached-reference summaries used by front-page style documents
- Read replicas (a successful write may include a replication `note`)

If your application needs to *observe* one of those views after a write, wait and read or search again with your own timeout and backoff. This library intentionally does not ship polling helpers, so that applications do not confuse visibility waits with integrity guarantees.
