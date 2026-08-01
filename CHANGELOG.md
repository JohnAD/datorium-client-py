# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Initial pure-Python smart client for DatoriumDB v0.0.5.
- Synchronous `Client` and asynchronous `AsyncClient` over httpx.
- Raw dictionary CRUD, search, references, and establishment routing.
- Typed collections for dataclasses and Pydantic v2 models.
- Internal ordered JSON, Datorium schema, and RFC 6902 patch support.
- Opt-in two-shard Todo Compose integration via `./start_integration_test.sh`.

### Changed

- Compatibility target is DatoriumDB **v0.0.5** (HTTP API `v1` unchanged).
- Contract goldens refreshed for hint-free `wrongMachine` envelopes (`configVersion` diagnostic only).
- `WriteResult.version_before` populated from patch `versions.before`.
- `wrongMachine` bounce fields documented as deprecated/parse-only; routing always re-establishes.
- Establishment is automatic on first routed use / typed bind; `establish()` is optional for catalog checks and refresh.
- `Config.collections` applies a catalog check on the first automatic establish.
- `Collection.bind_async` is now `async` and auto-establishes like sync `bind`.
