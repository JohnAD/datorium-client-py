"""Shard, searchpath, and refs unit tests."""

from __future__ import annotations

import pytest

from datorium_client import refs, searchpath, shard


def test_sharding_prefix_ignores_early_periods() -> None:
    assert shard.slot("abcdef.rest") == shard.raw_slot("abcdef")


def test_range_coverage() -> None:
    ranges = [shard.parse_range("00-7F"), shard.parse_range("80-FF")]
    shard.validate_full_coverage(ranges)
    with pytest.raises(ValueError, match="incomplete"):
        shard.validate_full_coverage([shard.parse_range("00-7F")])


def test_searchpath_encode() -> None:
    assert searchpath.encode_string_value("open") == "6F70656E"
    assert searchpath.encode_string_value("") == "empty"
    assert searchpath.equals_string_segments("open") == ["6F70656E"]


def test_refs() -> None:
    ref, ok = refs.parse_ref("@__Todos__abc")
    assert ok and ref is not None
    assert ref.collection == "Todos"
    assert ref.id == "abc"
    assert refs.format_cached("Todos", "abc") == "@@__Todos__abc"
