"""RFC 6901 JSON Pointer helpers."""

from __future__ import annotations


def escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def unescape(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def parse_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer {pointer!r}")
    return [unescape(part) for part in pointer[1:].split("/")]


def format_pointer(segments: list[str]) -> str:
    if not segments:
        return ""
    return "/" + "/".join(escape(s) for s in segments)


def parse_array_index(segment: str, *, allow_append: bool = False) -> int | None:
    """Return index, or None for '-' when allow_append."""
    if allow_append and segment == "-":
        return None
    if segment == "" or (segment.startswith("0") and segment != "0"):
        raise ValueError(f"invalid array index {segment!r}")
    if not segment.isdigit():
        raise ValueError(f"invalid array index {segment!r}")
    return int(segment)
