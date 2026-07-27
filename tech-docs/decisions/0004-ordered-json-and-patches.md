# 0004. Pure-Python ordered JSON, schema, and RFC 6902

## Status

Accepted

## Context

Go clients and the database depend on `ojson` for ordered objects, exact number lexemes, Void vs Null, Datorium schemas, and schema-aware patches. No third-party Python library combines these semantics.

## Decision

Implement an internal compatibility layer under `datorium_client._json`, `_schema`, and `_patch` using stdlib `json` hooks and insertion-ordered structures. Do not publish a separate general-purpose ojson package in this release. Do not use generic JSON Patch libraries as the compatibility core.

## Consequences

Significant implementation and golden-test surface. The `_json` types stay private. Public read surfaces (`ReadResult.sot` / `extra_fields` / `cache_summaries`, `CollectionItem.extra_fields`) expose `OrderedDict` views with `Decimal` numbers and `Null` / `Void` sentinels—Python can carry exact decimals; Go keeps number lexemes as text for the same reason.
