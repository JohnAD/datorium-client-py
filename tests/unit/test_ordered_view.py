"""Public OrderedDict / Decimal / Null / Void view of internal JSON."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from datorium_client import Null, Void
from datorium_client._json import loads
from datorium_client.ordered import as_ordered


def test_as_ordered_preserves_order_and_decimal() -> None:
    doc = loads('{"z":0.25E2,"a":null,"b":true}')
    view = as_ordered(doc)
    assert isinstance(view, OrderedDict)
    assert list(view.keys()) == ["z", "a", "b"]
    assert view["z"] == Decimal("0.25E2")
    assert view["a"] is Null
    assert view["b"] is True


def test_void_maps_to_public_void() -> None:
    from datorium_client._json.value import VOID

    assert as_ordered(VOID) is Void


def test_from_python_accepts_decimal_and_null() -> None:
    from datorium_client._json.value import JSONNull, JSONNumber, from_python

    num = from_python(Decimal("12.50"))
    assert isinstance(num, JSONNumber)
    assert num.text == "12.5"
    assert isinstance(from_python(Null), JSONNull)
