"""ULID helpers for document and operation IDs."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Generate a Crockford-base32 ULID (26 chars)."""
    ts = int(time.time() * 1000)
    if ts < 0 or ts >= 2**48:
        raise ValueError("timestamp out of ULID range")
    entropy = os.urandom(10)
    # 48-bit time + 80-bit entropy = 128 bits → 26 base32 chars
    value = (ts << 80) | int.from_bytes(entropy, "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_document_id() -> str:
    return new_ulid()


def new_operation_id() -> str:
    return new_ulid()
