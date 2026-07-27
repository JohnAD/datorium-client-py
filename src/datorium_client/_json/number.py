"""JSON number grammar, preparation, and rational equality."""

from __future__ import annotations

import re
from fractions import Fraction

_NUMBER_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")
_INT_RE = re.compile(r"^(0|[1-9][0-9]*)$")


def is_valid_number(text: str) -> bool:
    return bool(_NUMBER_RE.fullmatch(text))


def prepare_number(text: str) -> str:
    """Hygiene for constructor input; not used during decode."""
    s = text.strip()
    if s.endswith("."):
        left = s[:-1]
        if left in ("", "-"):
            raise ValueError(f"invalid number: {text!r}")
        sign = ""
        digits = left
        if left.startswith("-"):
            sign = "-"
            digits = left[1:]
        if not _INT_RE.fullmatch(digits):
            raise ValueError(f"invalid number: {text!r}")
        s = f"{sign}0.{digits}E{len(digits)}"
    s = s.replace("e", "E")
    if not is_valid_number(s):
        raise ValueError(f"invalid number: {text!r}")
    return s


def parse_json_number_rat(text: str) -> Fraction:
    if not is_valid_number(text):
        raise ValueError(f"invalid number: {text!r}")
    base = text
    exp = 0
    for i, ch in enumerate(text):
        if ch in "eE":
            base = text[:i]
            exp = int(text[i + 1 :])
            break
    sign = 1
    if base.startswith("-"):
        sign = -1
        base = base[1:]
    fraction_digits = 0
    if "." in base:
        whole, frac = base.split(".", 1)
        fraction_digits = len(frac)
        digits = whole + frac
    else:
        digits = base
    numerator = sign * int(digits, 10)
    scale = fraction_digits - exp
    if scale < 0:
        return Fraction(numerator * (10 ** (-scale)), 1)
    return Fraction(numerator, 10**scale)


def values_equal_number(a: str, b: str) -> bool:
    try:
        return parse_json_number_rat(a) == parse_json_number_rat(b)
    except ValueError:
        return a == b
