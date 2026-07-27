"""Schema normalize / reorder tests."""

from __future__ import annotations

import pytest

from datorium_client._json import dumps, loads
from datorium_client._schema import SchemaError, apply_schema, compile_schema

PET_SCHEMA = """
{
  "kind": "object",
  "children": [
    { "name": "name", "kind": "string", "required": true, "min_length": 1 },
    { "name": "age", "kind": "number", "integer": true, "min": 0 },
    { "name": "height_units", "kind": "string", "enum": ["inches", "centimeters"], "default": "inches" },
    { "name": "email", "kind": "string", "format": "email", "nullable": true },
    { "name": "tags", "kind": "array", "items": { "kind": "string", "min_length": 1 } }
  ]
}
"""


def test_schema_reorder_and_defaults() -> None:
    schema = compile_schema(PET_SCHEMA)
    doc = loads('{"nickname":"Whiff","tags":["small"],"age":3,"name":"Whiffles"}')
    out = apply_schema(doc, schema)
    assert dumps(out) == (
        '{"name":"Whiffles","age":3,"height_units":"inches","tags":["small"],"nickname":"Whiff"}'
    )


def test_required_missing() -> None:
    schema = compile_schema(PET_SCHEMA)
    with pytest.raises(SchemaError, match="required"):
        apply_schema(loads('{"age":3}'), schema)
