"""Access-language command construction."""

from __future__ import annotations

from typing import Any

from datorium_client._json.codec import dumps
from datorium_client._json.value import JSONObject, JSONValue, from_python, new_object, new_string
from datorium_client.ids import new_operation_id


def build_command(word: str, target: str, parm: str, detail: dict[str, Any] | None) -> str:
    obj = from_python(detail or {})
    if not isinstance(obj, JSONObject):
        raise TypeError("detail must be an object")
    return f"{word} {target} {parm} {dumps(obj)}"


def build_command_ordered(word: str, target: str, parm: str, detail: JSONObject) -> str:
    return f"{word} {target} {parm} {dumps(detail)}"


def ensure_operation_id(detail: dict[str, Any]) -> dict[str, Any]:
    out = dict(detail)
    if "operationId" not in out:
        out["operationId"] = new_operation_id()
    return out


def ensure_operation_id_object(detail: JSONObject) -> JSONObject:
    if not detail.has("operationId"):
        detail.set("operationId", new_string(new_operation_id()))
    return detail


def detail_from_mapping(data: dict[str, Any]) -> JSONObject:
    obj = from_python(data)
    if not isinstance(obj, JSONObject):
        raise TypeError("detail must be an object")
    return obj


def ordered_from_pairs(pairs: list[tuple[str, JSONValue]]) -> JSONObject:
    obj = new_object()
    for k, v in pairs:
        obj.set(k, v)
    return obj
