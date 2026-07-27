# 0005. Dataclass and Pydantic typed collections

## Status

Accepted

## Context

Application authors want dataclasses and commonly use Pydantic with ORMs.

## Decision

- Support stdlib dataclasses (via Pydantic `TypeAdapter`) and Pydantic v2 `BaseModel`.
- Expose both raw dict APIs and typed `Collection[T]` / bound clients.
- Map wire keys via dataclass metadata or Pydantic serialization aliases.
- Keep non-schema extra fields separately on `CollectionItem`.
- At bind time, strictly compare model and server **shape** (names, order, nested kinds, arrays, requiredness, nullability). Fail on untranslatable constraints. Do not require exact JSON Schema equality.
- Support snapshot-diff patches and explicit patch builders equally.

## Consequences

Binding can reject models that look valid to Pydantic alone. Users must keep field declaration order aligned with Datorium schemas.
