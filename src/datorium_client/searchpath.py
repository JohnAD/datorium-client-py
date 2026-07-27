"""Search result path encoding and shard slots."""

from __future__ import annotations

from datorium_client import shard

ENCODE_NULL = "null"


def encode_string_value(s: str) -> str:
    if s == "":
        return "empty"
    return s.encode("utf-8").hex().upper()


def encode_truth(b: bool) -> str:
    return "true" if b else "false"


def shard_input(segments: list[str]) -> str:
    return "/".join(segments)


def shard_slot(segments: list[str]) -> int:
    return shard.raw_slot(shard_input(segments))


def equals_string_segments(*values: str) -> list[str]:
    return [encode_string_value(v) for v in values]
