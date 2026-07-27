"""Ordered JSON codec golden tests."""

from __future__ import annotations

import pytest

from datorium_client._json import dumps, is_valid_number, loads, prepare_number
from datorium_client._json.value import JSONNumber, JSONObject


def test_preserve_order_and_number_text() -> None:
    text = '{"z":0.25E2,"a":"x","nested":{"b":true,"a":null}}'
    doc = loads(text)
    assert dumps(doc) == text
    assert isinstance(doc, JSONObject)
    z = doc.get("z")
    assert isinstance(z, JSONNumber)
    assert z.text == "0.25E2"


def test_trailing_tokens_rejected() -> None:
    with pytest.raises(ValueError, match="trailing"):
        loads("{} {}")


def test_pretty_indent() -> None:
    doc = loads('{"name":"Whiffles","ratings":[3.2,null]}')
    want = "{\n  \"name\": \"Whiffles\",\n  \"ratings\": [\n    3.2,\n    null\n  ]\n}"
    assert dumps(doc, indent=2) == want


def test_string_escape() -> None:
    doc = loads('"line\\nquote\\""')
    assert dumps(doc) == '"line\\nquote\\""'


@pytest.mark.parametrize(
    "text,valid",
    [
        ("0", True),
        ("-0", True),
        ("25", True),
        ("25.0", True),
        ("0.25E2", True),
        ("1e-9", True),
        ("", False),
        ("01", False),
        ("25.", False),
        (".25", False),
        (" 25 ", False),
        ("NaN", False),
        ("Infinity", False),
    ],
)
def test_is_valid_number(text: str, valid: bool) -> None:
    assert is_valid_number(text) is valid


def test_prepare_number() -> None:
    assert prepare_number(" 25. ") == "0.25E2"
