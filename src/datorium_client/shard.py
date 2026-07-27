"""Document sharding helpers (CRC32 IEEE → 8-bit slot)."""

from __future__ import annotations

import binascii
from dataclasses import dataclass


def slot(document_id: str) -> int:
    prefix = _sharding_prefix(document_id)
    return binascii.crc32(prefix.encode("utf-8")) & 0xFF


def slot_hex(document_id: str) -> str:
    return f"{slot(document_id):02X}"


def raw_slot(input_str: str) -> int:
    return binascii.crc32(input_str.encode("utf-8")) & 0xFF


def raw_slot_hex(input_str: str) -> str:
    return f"{raw_slot(input_str):02X}"


def _sharding_prefix(document_id: str) -> str:
    for i, ch in enumerate(document_id):
        if ch != ".":
            continue
        if i < 6:
            continue
        return document_id[:i]
    return document_id


@dataclass(frozen=True)
class Range:
    start: int
    end: int
    raw: str

    def contains(self, slot_value: int) -> bool:
        return self.start <= slot_value <= self.end


def parse_range(raw: str) -> Range:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty shard range")
    if "-" not in raw:
        s = _parse_slot(raw)
        return Range(start=s, end=s, raw=raw.upper())
    parts = raw.split("-")
    if len(parts) != 2:
        raise ValueError(f"invalid shard range {raw!r}")
    start = _parse_slot(parts[0])
    end = _parse_slot(parts[1])
    if start > end:
        raise ValueError(f"shard range start after end: {raw!r}")
    return Range(start=start, end=end, raw=raw.upper())


def _parse_slot(raw: str) -> int:
    raw = raw.strip()
    if not raw or len(raw) > 2:
        raise ValueError(f"invalid shard slot {raw!r}")
    try:
        return int(raw, 16)
    except ValueError as exc:
        raise ValueError(f"invalid shard slot {raw!r}") from exc


def validate_full_coverage(ranges: list[Range]) -> None:
    covered = [False] * 256
    for r in ranges:
        for i in range(r.start, r.end + 1):
            if covered[i]:
                raise ValueError(f"overlapping shard slot {i:02X}")
            covered[i] = True
    for i, ok in enumerate(covered):
        if not ok:
            raise ValueError(f"incomplete shard map: missing slot {i:02X}")
