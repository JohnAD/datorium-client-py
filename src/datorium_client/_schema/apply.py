"""Apply and validate values against compiled schemas."""

from __future__ import annotations

from datorium_client._json.number import parse_json_number_rat
from datorium_client._json.value import (
    JSONArray,
    JSONBoolean,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    clone_value,
    is_void,
    new_array,
    new_object,
)
from datorium_client._schema.compile import CompiledSchema, SchemaEntry, SchemaError


def apply_schema(value: JSONValue, schema: CompiledSchema) -> JSONValue:
    return _normalize(value, schema.root, path="")


def validate_schema(value: JSONValue, schema: CompiledSchema) -> None:
    apply_schema(value, schema)


def _normalize(value: JSONValue | VoidType, entry: SchemaEntry, path: str) -> JSONValue:
    if is_void(value):
        raise SchemaError("value is missing", path or "$")
    assert not isinstance(value, VoidType)

    if isinstance(value, JSONNull):
        if entry.kind == "null" or entry.nullable:
            return JSONNull()
        raise SchemaError("null not allowed", _disp(path))

    kind_ok = {
        "object": JSONObject,
        "array": JSONArray,
        "string": JSONString,
        "number": JSONNumber,
        "boolean": JSONBoolean,
        "null": JSONNull,
    }[entry.kind]
    if not isinstance(value, kind_ok):
        raise SchemaError(f"expected {entry.kind}", _disp(path))

    if entry.kind == "object":
        assert isinstance(value, JSONObject)
        return _normalize_object(value, entry, path)
    if entry.kind == "array":
        assert isinstance(value, JSONArray)
        return _normalize_array(value, entry, path)
    if entry.kind == "string":
        assert isinstance(value, JSONString)
        _validate_string(value, entry, path)
        return value.clone()
    if entry.kind == "number":
        assert isinstance(value, JSONNumber)
        _validate_number(value, entry, path)
        return value.clone()
    if entry.kind == "boolean":
        assert isinstance(value, JSONBoolean)
        return value.clone()
    return value.clone()


def _normalize_object(value: JSONObject, entry: SchemaEntry, path: str) -> JSONObject:
    source = {k: v for k, v in value.items_non_void()}
    out = new_object()
    for child in entry.children:
        child_path = f"{path}.{child.name}" if path else child.name
        if child.name in source:
            out.set(child.name, _normalize(source[child.name], child, child_path))
        elif child.has_default and child.default is not None:
            out.set(child.name, _normalize(clone_value(child.default), child, child_path))
        elif child.required:
            raise SchemaError("required field is missing", _quote_field(child.name, path))
        # else optional absent — skip
    # Unknowns in source order
    known = set(entry.child_by_name)
    for k, v in value.items_non_void():
        if k not in known:
            out.set(k, clone_value(v))
    return out


def _normalize_array(value: JSONArray, entry: SchemaEntry, path: str) -> JSONArray:
    items: list[JSONValue] = []
    for i, item in enumerate(value.items):
        if is_void(item):
            continue
        if entry.items is not None:
            items.append(_normalize(item, entry.items, f"{path}.{i}" if path else str(i)))
        else:
            items.append(clone_value(item))
    return new_array(items)


def _validate_string(value: JSONString, entry: SchemaEntry, path: str) -> None:
    runes = len(value.value)
    if entry.min_length is not None and runes < entry.min_length:
        raise SchemaError(
            f"string length is below min_length {entry.min_length}",
            _disp(path),
        )
    if entry.max_length is not None and runes > entry.max_length:
        raise SchemaError(
            f"string length is above max_length {entry.max_length}",
            _disp(path),
        )
    if entry.enum_set and value.value not in entry.enum_set:
        raise SchemaError("value not in enum", _disp(path))
    if entry.format_validator is not None and not entry.format_validator(value.value):
        raise SchemaError(f"string does not match format {entry.format}", _disp(path))


def _validate_number(value: JSONNumber, entry: SchemaEntry, path: str) -> None:
    rat = parse_json_number_rat(value.text)
    if entry.integer and rat.denominator != 1:
        raise SchemaError("expected integer number", _disp(path))
    if entry.min_rat is not None and rat < entry.min_rat:
        raise SchemaError(f"number below min {entry.min_text}", _disp(path))
    if entry.max_rat is not None and rat > entry.max_rat:
        raise SchemaError(f"number above max {entry.max_text}", _disp(path))


def _disp(path: str) -> str:
    return path if path else "$"


def _quote_field(name: str, parent: str) -> str:
    import json

    quoted = json.dumps(name)
    if not parent:
        return quoted
    return f"{parent}.{quoted}"
