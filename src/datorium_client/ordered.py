"""Public ordered JSON view types (hides internal _json representation)."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any

from datorium_client._json.value import (
    JSONArray,
    JSONBoolean,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    is_void,
)


class NullType:
    """JSON null (field present, value unknown/null)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Null"

    def __bool__(self) -> bool:
        return False


class VoidTypePublic:
    """Absence marker (path/field does not exist; never serialized)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Void"

    def __bool__(self) -> bool:
        return False


Null = NullType()
Void = VoidTypePublic()

OrderedJSON = OrderedDict[str, Any] | list[Any] | str | bool | Decimal | NullType | VoidTypePublic


def as_ordered(value: JSONValue | VoidType | None) -> Any:
    """Convert an internal JSON value to OrderedDict / list / Decimal / Null / Void."""
    if value is None or is_void(value):
        return Void
    if isinstance(value, JSONNull):
        return Null
    if isinstance(value, JSONBoolean):
        return value.value
    if isinstance(value, JSONString):
        return value.value
    if isinstance(value, JSONNumber):
        return Decimal(value.text)
    if isinstance(value, JSONArray):
        return [as_ordered(item) for item in value.items if not is_void(item)]
    if isinstance(value, JSONObject):
        out: OrderedDict[str, Any] = OrderedDict()
        for key, item in value.items_non_void():
            out[key] = as_ordered(item)
        return out
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def as_ordered_object(value: JSONObject | None) -> OrderedDict[str, Any] | None:
    if value is None:
        return None
    converted = as_ordered(value)
    if not isinstance(converted, OrderedDict):
        raise TypeError("expected object")
    return converted
