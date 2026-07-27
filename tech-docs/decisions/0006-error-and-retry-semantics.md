# 0006. Error and retry semantics

## Status

Accepted

## Context

DatoriumDB returns logical/business outcomes in JSON envelopes with HTTP 200. Non-2xx statuses indicate transport/protocol problems (for example, wrong URL), not “document missing”.

## Decision

- HTTP 200 + `ok:true` → success
- HTTP 200 + `ok:false` → `AppError` (including `documentNotFound`)
- Non-2xx → `TransportError` (HTTP 404 means wrong endpoint)
- Marshal each command line once before retries
- On `wrongMachine`: always re-fetch establishment from the establishment server, then re-route from that document (bounded by `wrong_machine_retries`)
- Ignore bounce `correctServer` / `baseURL`; treat bounce `configVersion` as diagnostic only (not authoritative)
- Support configurable transport retries, create ambiguity verification, and version-mismatch patch retry
- Stale-read policy is configurable (surface / failover / prefer-SOT options)
- Client retries do **not** provide database integrity; DatoriumDB owns integrity

## Consequences

User docs must teach the application-channel model explicitly so callers do not misuse HTTP status codes.
