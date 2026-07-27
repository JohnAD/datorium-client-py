"""Ordered JSON value model with Void vs Null distinction."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JSONKind(StrEnum):
    VOID = "void"
    OBJECT = "object"
    ARRAY = "array"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"


class VoidType:
    """Sentinel for absence (never serialized)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "VOID"

    def __bool__(self) -> bool:
        return False


VOID = VoidType()


def is_void(value: Any) -> bool:
    return value is VOID or isinstance(value, VoidType)


def new_void() -> VoidType:
    return VOID


@dataclass
class JSONNull:
    kind: JSONKind = field(default=JSONKind.NULL, init=False)

    def clone(self) -> JSONNull:
        return JSONNull()


@dataclass
class JSONBoolean:
    value: bool
    kind: JSONKind = field(default=JSONKind.BOOLEAN, init=False)

    def clone(self) -> JSONBoolean:
        return JSONBoolean(self.value)


@dataclass
class JSONString:
    value: str
    kind: JSONKind = field(default=JSONKind.STRING, init=False)

    def clone(self) -> JSONString:
        return JSONString(self.value)


@dataclass
class JSONNumber:
    text: str
    kind: JSONKind = field(default=JSONKind.NUMBER, init=False)

    def clone(self) -> JSONNumber:
        return JSONNumber(self.text)


@dataclass
class JSONArray:
    items: list[JSONValue] = field(default_factory=list)
    kind: JSONKind = field(default=JSONKind.ARRAY, init=False)

    def clone(self) -> JSONArray:
        return JSONArray([clone_value(v) for v in self.items if not is_void(v)])

    def __iter__(self) -> Iterator[JSONValue]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


@dataclass
class JSONObject:
    """Ordered object as a list of key/value pairs."""

    fields: list[tuple[str, JSONValue]] = field(default_factory=list)
    kind: JSONKind = field(default=JSONKind.OBJECT, init=False)

    def keys(self) -> list[str]:
        return [k for k, v in self.fields if not is_void(v)]

    def items_non_void(self) -> list[tuple[str, JSONValue]]:
        return [(k, v) for k, v in self.fields if not is_void(v)]

    def get(self, key: str) -> JSONValue | VoidType:
        for k, v in self.fields:
            if k == key:
                return v if not is_void(v) else VOID
        return VOID

    def has(self, key: str) -> bool:
        return any(k == key and not is_void(v) for k, v in self.fields)

    def set(self, key: str, value: JSONValue | VoidType) -> None:
        if is_void(value):
            self.remove(key)
            return
        for i, (k, _) in enumerate(self.fields):
            if k == key:
                self.fields[i] = (key, value)  # type: ignore[assignment]
                return
        self.fields.append((key, value))  # type: ignore[arg-type]

    def remove(self, key: str) -> bool:
        for i, (k, _) in enumerate(self.fields):
            if k == key:
                del self.fields[i]
                return True
        return False

    def clone(self) -> JSONObject:
        return JSONObject([(k, clone_value(v)) for k, v in self.fields if not is_void(v)])


JSONValue = JSONObject | JSONArray | JSONString | JSONNumber | JSONBoolean | JSONNull


def clone_value(value: JSONValue | VoidType) -> JSONValue | VoidType:
    if is_void(value):
        return VOID
    assert not isinstance(value, VoidType)
    return value.clone()


def new_null() -> JSONNull:
    return JSONNull()


def new_boolean(value: bool) -> JSONBoolean:
    return JSONBoolean(value)


def new_string(value: str) -> JSONString:
    if not isinstance(value, str):
        raise TypeError("string value required")
    # Reject lone surrogates / ensure valid unicode by round-trip encode
    value.encode("utf-8")
    return JSONString(value)


def new_number(text: str) -> JSONNumber:
    from datorium_client._json.number import is_valid_number

    if not is_valid_number(text):
        raise ValueError(f"invalid JSON number: {text!r}")
    return JSONNumber(text)


def new_object(pairs: list[tuple[str, JSONValue]] | None = None) -> JSONObject:
    obj = JSONObject()
    if pairs:
        for k, v in pairs:
            obj.set(k, v)
    return obj


def new_array(items: list[JSONValue] | None = None) -> JSONArray:
    return JSONArray(list(items or []))


def to_python(value: JSONValue | VoidType) -> Any:
    """Convert to plain Python (dict/list/...). Void becomes missing (None returned)."""
    if is_void(value):
        return None
    if isinstance(value, JSONNull):
        return None
    if isinstance(value, JSONBoolean):
        return value.value
    if isinstance(value, JSONString):
        return value.value
    if isinstance(value, JSONNumber):
        return value.text
    if isinstance(value, JSONArray):
        return [to_python(v) for v in value.items if not is_void(v)]
    if isinstance(value, JSONObject):
        return {k: to_python(v) for k, v in value.items_non_void()}
    raise TypeError(f"unsupported value: {type(value)!r}")


def from_python(data: Any) -> JSONValue:
    """Build a JSONValue from plain Python structures (numbers become decimal text)."""
    from decimal import Decimal

    # Public ordered view sentinels (lazy import avoids cycles).
    from datorium_client.ordered import Null, Void

    if data is None or data is Null:
        return new_null()
    if data is Void:
        raise TypeError("Void cannot be converted to a JSON value")
    if isinstance(data, bool):
        return new_boolean(data)
    if isinstance(data, str):
        return new_string(data)
    if isinstance(data, Decimal):
        text = format(data, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return new_number(text or "0")
    if isinstance(data, int) and not isinstance(data, bool):
        return new_number(str(data))
    if isinstance(data, float):
        if data != data or data in (float("inf"), float("-inf")):
            raise ValueError("NaN/Inf not allowed")
        # Match Go FormatFloat('g', -1, 64) roughly
        text = format(data, "g").replace("e", "E") if "e" in format(data, "g") else format(data, "g")
        # Prefer simple int-like floats as integers when exact
        if data.is_integer() and abs(data) < 1e15:
            text = str(int(data))
        return new_number(text)
    if isinstance(data, dict):
        obj = new_object()
        for k, v in data.items():
            if not isinstance(k, str):
                raise TypeError("object keys must be strings")
            if v is Void:
                continue
            obj.set(k, from_python(v))
        return obj
    if isinstance(data, (list, tuple)):
        return new_array([from_python(v) for v in data if v is not Void])
    raise TypeError(f"cannot convert {type(data)!r} to JSONValue")
