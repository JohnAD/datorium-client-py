"""Compile Datorium/ojson schema documents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from datorium_client._json.codec import loads
from datorium_client._json.number import parse_json_number_rat
from datorium_client._json.value import (
    JSONArray,
    JSONBoolean,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    is_void,
)
from datorium_client._schema.formats import DEFAULT_FORMAT_REGISTRY, StringFormatRegistry, Validator

_DESC_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$")
_KNOWN_KEYS = {
    "kind",
    "name",
    "children",
    "default",
    "required",
    "nullable",
    "min",
    "max",
    "integer",
    "enum",
    "min_length",
    "max_length",
    "format",
    "items",
    "custom",
}
_KINDS = {"object", "array", "string", "number", "boolean", "null"}


class SchemaError(ValueError):
    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)


@dataclass
class SchemaEntry:
    name: str
    kind: str
    children: list[SchemaEntry] = field(default_factory=list)
    child_by_name: dict[str, SchemaEntry] = field(default_factory=dict)
    items: SchemaEntry | None = None
    default: JSONValue | None = None
    has_default: bool = False
    required: bool = False
    nullable: bool = False
    min_rat: Fraction | None = None
    max_rat: Fraction | None = None
    min_text: str | None = None
    max_text: str | None = None
    integer: bool = False
    enum: list[str] = field(default_factory=list)
    enum_set: set[str] = field(default_factory=set)
    min_length: int | None = None
    max_length: int | None = None
    format: str | None = None
    format_validator: Validator | None = None
    descriptions: dict[str, str] = field(default_factory=dict)
    custom: JSONValue | None = None


@dataclass
class CompiledSchema:
    root: SchemaEntry
    formats: dict[str, Validator]


def compile_schema(
    source: str | bytes | JSONValue | dict[str, Any],
    *,
    formats: StringFormatRegistry | None = None,
) -> CompiledSchema:
    registry = formats or DEFAULT_FORMAT_REGISTRY
    snapshot = registry.snapshot()
    if isinstance(source, (str, bytes)):
        doc = loads(source) if isinstance(source, str) else loads(source.decode("utf-8"))
    elif isinstance(source, dict):
        from datorium_client._json.value import from_python

        doc = from_python(source)
    else:
        doc = source
    if not isinstance(doc, JSONObject):
        raise SchemaError("schema root must be an object")
    root = _compile_entry(doc, path="$", allow_name=False, formats=snapshot)
    return CompiledSchema(root=root, formats=snapshot)


def _compile_entry(
    obj: JSONObject,
    *,
    path: str,
    allow_name: bool,
    formats: dict[str, Validator],
) -> SchemaEntry:
    for key, _ in obj.items_non_void():
        if key in _KNOWN_KEYS:
            continue
        if key.startswith("description-"):
            lang = key[len("description-") :]
            if not _DESC_LANG.fullmatch(lang):
                raise SchemaError(f"invalid description language {lang!r}", path)
            continue
        raise SchemaError(f"unknown schema field {key!r}", path)

    kind_v = obj.get("kind")
    if is_void(kind_v) or not isinstance(kind_v, JSONString):
        raise SchemaError("kind is required", path)
    kind = kind_v.value
    if kind not in _KINDS:
        raise SchemaError(f"invalid kind {kind!r}", path)

    name = ""
    name_v = obj.get("name")
    if not is_void(name_v):
        if not isinstance(name_v, JSONString):
            raise SchemaError("name must be a string", path)
        name = name_v.value
    elif allow_name:
        raise SchemaError("name is required", path)

    entry = SchemaEntry(name=name, kind=kind)
    req = obj.get("required")
    if not is_void(req):
        if not isinstance(req, JSONBoolean):
            raise SchemaError("required must be boolean", path)
        entry.required = req.value
    nul = obj.get("nullable")
    if not is_void(nul):
        if not isinstance(nul, JSONBoolean):
            raise SchemaError("nullable must be boolean", path)
        entry.nullable = nul.value

    if kind == "object":
        children_v = obj.get("children")
        if not is_void(children_v):
            if not isinstance(children_v, JSONArray):
                raise SchemaError("children must be an array", path)
            for i, child in enumerate(children_v.items):
                if not isinstance(child, JSONObject):
                    raise SchemaError("child schema must be object", f"{path}.children.{i}")
                child_entry = _compile_entry(
                    child, path=f"{path}.children.{i}", allow_name=True, formats=formats
                )
                if child_entry.name in entry.child_by_name:
                    raise SchemaError(f"duplicate child {child_entry.name!r}", path)
                entry.children.append(child_entry)
                entry.child_by_name[child_entry.name] = child_entry
    elif kind == "array":
        items_v = obj.get("items")
        if not is_void(items_v):
            if not isinstance(items_v, JSONObject):
                raise SchemaError("items must be an object", path)
            entry.items = _compile_entry(
                items_v, path=f"{path}.items", allow_name=False, formats=formats
            )
    elif kind == "string":
        _compile_string_constraints(obj, entry, path, formats)
    elif kind == "number":
        _compile_number_constraints(obj, entry, path)

    custom = obj.get("custom")
    if not is_void(custom) and not isinstance(custom, type(None)):
        from datorium_client._json.value import clone_value

        if not is_void(custom):
            entry.custom = clone_value(custom)  # type: ignore[assignment]

    for key, val in obj.items_non_void():
        if key.startswith("description-") and isinstance(val, JSONString):
            entry.descriptions[key] = val.value

    default_v = obj.get("default")
    if not is_void(default_v):
        entry.default = default_v  # type: ignore[assignment]
        entry.has_default = True
        # Validate default against this entry (shallow kind check)
        _validate_default(entry, default_v, path)  # type: ignore[arg-type]

    return entry


def _compile_string_constraints(
    obj: JSONObject, entry: SchemaEntry, path: str, formats: dict[str, Validator]
) -> None:
    for key, attr in (("min_length", "min_length"), ("max_length", "max_length")):
        v = obj.get(key)
        if is_void(v):
            continue
        if not isinstance(v, JSONNumber):
            raise SchemaError(f"{key} must be a number", path)
        n = int(parse_json_number_rat(v.text))
        setattr(entry, attr, n)
    enum_v = obj.get("enum")
    if not is_void(enum_v):
        if not isinstance(enum_v, JSONArray):
            raise SchemaError("enum must be an array", path)
        for item in enum_v.items:
            if not isinstance(item, JSONString):
                raise SchemaError("enum values must be strings", path)
            entry.enum.append(item.value)
        entry.enum_set = set(entry.enum)
    fmt = obj.get("format")
    if not is_void(fmt):
        if not isinstance(fmt, JSONString):
            raise SchemaError("format must be a string", path)
        if fmt.value not in formats:
            raise SchemaError(f"unknown string format {fmt.value!r}", path)
        entry.format = fmt.value
        entry.format_validator = formats[fmt.value]


def _compile_number_constraints(obj: JSONObject, entry: SchemaEntry, path: str) -> None:
    for key, attr_rat, attr_text in (
        ("min", "min_rat", "min_text"),
        ("max", "max_rat", "max_text"),
    ):
        v = obj.get(key)
        if is_void(v):
            continue
        if not isinstance(v, JSONNumber):
            raise SchemaError(f"{key} must be a number", path)
        setattr(entry, attr_rat, parse_json_number_rat(v.text))
        setattr(entry, attr_text, v.text)
    integ = obj.get("integer")
    if not is_void(integ):
        if not isinstance(integ, JSONBoolean):
            raise SchemaError("integer must be boolean", path)
        entry.integer = integ.value


def _validate_default(entry: SchemaEntry, value: JSONValue, path: str) -> None:
    if isinstance(value, JSONNull):
        if entry.kind != "null" and not entry.nullable:
            raise SchemaError("default null not allowed", path)
        return
    kind_map = {
        "object": JSONObject,
        "array": JSONArray,
        "string": JSONString,
        "number": JSONNumber,
        "boolean": JSONBoolean,
        "null": JSONNull,
    }
    expected = kind_map[entry.kind]
    if not isinstance(value, expected):
        raise SchemaError(f"default kind mismatch for {entry.kind}", path)
