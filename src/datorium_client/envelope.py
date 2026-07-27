"""DatoriumDB response envelope decoding."""

from __future__ import annotations

from dataclasses import dataclass, field

from datorium_client._json.codec import dumps, loads_bytes
from datorium_client._json.value import (
    JSONArray,
    JSONBoolean,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    is_void,
)
from datorium_client.errors import TransportError


@dataclass
class APIError:
    code: str = ""
    path: str = ""
    message: str = ""
    expected: JSONValue | VoidType | None = None
    actual: JSONValue | VoidType | None = None


@dataclass
class Result:
    ok: bool = False
    errors: list[APIError] = field(default_factory=list)
    env: JSONObject | None = None
    body: bytes = b""

    def first_error_code(self) -> str:
        return self.errors[0].code if self.errors else ""

    def string_field(self, key: str) -> str:
        if self.env is None:
            return ""
        return _as_string(self.env.get(key))

    def int_field(self, key: str) -> int:
        if self.env is None:
            return 0
        v = self.env.get(key)
        if is_void(v) or not isinstance(v, JSONNumber):
            return 0
        try:
            return int(v.text.split(".")[0].split("e")[0].split("E")[0])
        except ValueError:
            return 0

    def value_field(self, key: str) -> JSONValue | VoidType:
        from datorium_client._json.value import VOID

        if self.env is None:
            return VOID
        return self.env.get(key)


def decode_result(body: bytes) -> Result:
    try:
        env = loads_bytes(body)
    except ValueError as exc:
        raise TransportError(body=body.decode("utf-8", errors="replace"), err=exc) from exc
    if not isinstance(env, JSONObject):
        raise TransportError(body=body.decode("utf-8", errors="replace"), err=ValueError("expected object"))
    res = Result(env=env, body=body)
    ok_v = env.get("ok")
    if isinstance(ok_v, JSONBoolean):
        res.ok = ok_v.value
    err_list = env.get("errors")
    if isinstance(err_list, JSONArray):
        for item in err_list.items:
            if not isinstance(item, JSONObject):
                continue
            res.errors.append(
                APIError(
                    code=_as_string(item.get("code")),
                    path=_as_string(item.get("path")),
                    message=_as_string(item.get("message")),
                    expected=item.get("expected"),
                    actual=item.get("actual"),
                )
            )
    return res


def _as_string(v: JSONValue | VoidType | None) -> str:
    if v is None or is_void(v):
        return ""
    if isinstance(v, JSONString):
        return v.value
    if isinstance(v, JSONNumber):
        return v.text
    if isinstance(v, JSONBoolean):
        return "true" if v.value else "false"
    return dumps(v)
