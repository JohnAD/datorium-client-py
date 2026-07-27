"""Built-in and custom string format validators."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

Validator = Callable[[str], bool]

_TEL_RE = re.compile(r"[0-9+(). -]+")


def _email(value: str) -> bool:
    return value.count("@") == 1 and not value.startswith("@") and not value.endswith("@")


def _tel(value: str) -> bool:
    return value != "" and bool(_TEL_RE.fullmatch(value))


def _url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return bool(parsed.scheme and parsed.netloc)


_BUILTINS: dict[str, Validator] = {
    "email": _email,
    "tel": _tel,
    "url": _url,
}


class StringFormatRegistry:
    def __init__(self) -> None:
        self._custom: dict[str, Validator] = {}

    def register(self, name: str, validator: Validator) -> None:
        if not name:
            raise ValueError("format name required")
        if name in _BUILTINS:
            raise ValueError(f"cannot override built-in format {name!r}")
        if name in self._custom:
            raise ValueError(f"format already registered: {name!r}")
        self._custom[name] = validator

    def snapshot(self) -> dict[str, Validator]:
        return {**_BUILTINS, **self._custom}

    def validate(self, name: str, value: str, snapshot: dict[str, Validator] | None = None) -> bool:
        table = snapshot if snapshot is not None else self.snapshot()
        fn = table.get(name)
        if fn is None:
            return False
        return fn(value)


DEFAULT_FORMAT_REGISTRY = StringFormatRegistry()
