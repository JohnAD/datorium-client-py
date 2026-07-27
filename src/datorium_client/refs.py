"""Document reference parse/format helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RefKind(Enum):
    DIRECT = 1
    CACHED = 2


@dataclass(frozen=True)
class Ref:
    kind: RefKind
    collection: str
    id: str
    raw: str


def parse_ref(s: str) -> tuple[Ref | None, bool]:
    """Return (ref, ok). ok=False means not a reference string."""
    s = s.strip()
    if not s:
        return None, False
    if s.startswith("@@__"):
        kind = RefKind.CACHED
        rest = s[4:]
    elif s.startswith("@__"):
        kind = RefKind.DIRECT
        rest = s[3:]
    else:
        return None, False
    idx = rest.find("__")
    if idx <= 0 or idx + 2 >= len(rest):
        raise ValueError(f"invalid reference {s!r}")
    collection = rest[:idx]
    doc_id = rest[idx + 2 :]
    if not collection or not doc_id:
        raise ValueError(f"invalid reference {s!r}")
    return Ref(kind=kind, collection=collection, id=doc_id, raw=s), True


def format_direct(collection: str, doc_id: str) -> str:
    return f"@__{collection}__{doc_id}"


def format_cached(collection: str, doc_id: str) -> str:
    return f"@@__{collection}__{doc_id}"
