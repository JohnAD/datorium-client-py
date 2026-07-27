"""RFC 6902 patch tests."""

from __future__ import annotations

from datorium_client._json import dumps, loads
from datorium_client._patch import apply_patch, diff, parse_patch
from datorium_client._schema import compile_schema


def test_numeric_equality_empty_diff() -> None:
    assert len(diff(loads("25"), loads("25.0"))) == 0


def test_null_vs_missing_remove() -> None:
    patch = diff(loads('{"a":null}'), loads("{}"))
    assert len(patch) == 1
    assert patch.ops[0].op == "remove"


def test_apply_multi_op() -> None:
    doc = loads('{"name":"Whiffles","tags":["a"],"keep":1}')
    patch = parse_patch(
        [
            {"op": "replace", "path": "/name", "value": "Whiff"},
            {"op": "add", "path": "/tags/-", "value": "b"},
        ]
    )
    out = apply_patch(doc, patch)
    assert dumps(out) == '{"name":"Whiff","tags":["a","b"],"keep":1}'


def test_schema_default_no_diff() -> None:
    schema = compile_schema(
        {
            "kind": "object",
            "children": [
                {"name": "name", "kind": "string", "required": True},
                {
                    "name": "height_units",
                    "kind": "string",
                    "default": "inches",
                    "enum": ["inches", "centimeters"],
                },
            ],
        }
    )
    before = loads('{"name":"A"}')
    after = loads('{"name":"A","height_units":"inches"}')
    patch = diff(before, after, schema=schema)
    assert len(patch) == 0
