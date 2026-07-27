"""Encode/decode ordered JSON with exact number lexemes."""

from __future__ import annotations

import json
from typing import Any

from datorium_client._json.value import (
    VOID,
    JSONArray,
    JSONBoolean,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    is_void,
    new_array,
    new_boolean,
    new_null,
    new_number,
    new_object,
    new_string,
)


class _NumberStr(str):
    """Marker so object_hook can detect preserved number texts."""


def loads(text: str) -> JSONValue:
    if not isinstance(text, str):
        raise TypeError("loads expects str")
    # Validate UTF-8 round-trip
    text.encode("utf-8")
    return loads_bytes(text.encode("utf-8"))


def loads_bytes(data: bytes) -> JSONValue:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid UTF-8") from exc
    decoder = json.JSONDecoder(parse_int=_NumberStr, parse_float=_NumberStr)
    # Allow leading whitespace (JSON standard)
    start = 0
    while start < len(text) and text[start].isspace():
        start += 1
    try:
        raw, idx = decoder.raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    # Reject trailing tokens (allow only whitespace)
    if text[idx:].strip():
        raise ValueError("trailing tokens after JSON value")
    return _from_raw(raw)


def _from_raw(raw: Any) -> JSONValue:
    if raw is None:
        return new_null()
    if isinstance(raw, bool):
        return new_boolean(raw)
    if isinstance(raw, _NumberStr):
        return new_number(str(raw))
    if isinstance(raw, str):
        return new_string(raw)
    if isinstance(raw, list):
        return new_array([_from_raw(v) for v in raw])
    if isinstance(raw, dict):
        # json.loads preserves insertion order in 3.7+
        obj = new_object()
        for k, v in raw.items():
            obj.set(str(k), _from_raw(v))
        return obj
    raise ValueError(f"unexpected JSON type: {type(raw)!r}")


def dumps(value: JSONValue | VoidType, *, indent: int | None = None) -> str:
    if is_void(value):
        return ""
    if indent is not None and indent > 0:
        return _pretty(value, indent=indent, level=0)
    return _compact(value)


def _compact(value: JSONValue) -> str:
    if isinstance(value, JSONNull):
        return "null"
    if isinstance(value, JSONBoolean):
        return "true" if value.value else "false"
    if isinstance(value, JSONNumber):
        return value.text
    if isinstance(value, JSONString):
        return json.dumps(value.value, ensure_ascii=False)
    if isinstance(value, JSONArray):
        parts = [_compact(v) for v in value.items if not is_void(v)]
        return "[" + ",".join(parts) + "]"
    if isinstance(value, JSONObject):
        parts = [
            f"{json.dumps(k, ensure_ascii=False)}:{_compact(v)}"
            for k, v in value.items_non_void()
        ]
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"cannot encode {type(value)!r}")


def _pretty(value: JSONValue, *, indent: int, level: int) -> str:
    pad = " " * (level * indent)
    inner = " " * ((level + 1) * indent)
    if isinstance(value, JSONNull):
        return "null"
    if isinstance(value, JSONBoolean):
        return "true" if value.value else "false"
    if isinstance(value, JSONNumber):
        return value.text
    if isinstance(value, JSONString):
        return json.dumps(value.value, ensure_ascii=False)
    if isinstance(value, JSONArray):
        items = [v for v in value.items if not is_void(v)]
        if not items:
            return "[]"
        lines = [f"{inner}{_pretty(v, indent=indent, level=level + 1)}" for v in items]
        return "[\n" + ",\n".join(lines) + "\n" + pad + "]"
    if isinstance(value, JSONObject):
        fields = value.items_non_void()
        if not fields:
            return "{}"
        lines = [
            f"{inner}{json.dumps(k, ensure_ascii=False)}: {_pretty(v, indent=indent, level=level + 1)}"
            for k, v in fields
        ]
        return "{\n" + ",\n".join(lines) + "\n" + pad + "}"
    raise TypeError(f"cannot encode {type(value)!r}")


# Silence unused import warning for VOID used in type unions externally
_ = VOID
