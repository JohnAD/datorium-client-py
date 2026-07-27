"""Raw CRUD / search result types and helpers."""

from __future__ import annotations

import contextlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from datorium_client._json.value import (
    JSONArray,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    is_void,
)
from datorium_client.envelope import Result
from datorium_client.ordered import as_ordered, as_ordered_object


@dataclass
class ReadOptions:
    extra_fields: bool = False
    cache_summaries: bool = False


@dataclass
class ReplicationNote:
    code: str = ""
    message: str = ""
    required: list[str] = field(default_factory=list)
    acknowledged: list[str] = field(default_factory=list)
    unacknowledged: list[str] = field(default_factory=list)
    timeout_ms: int = 0
    raw: OrderedDict[str, Any] | None = None


@dataclass
class WriteResult:
    result: Result
    collection: str = ""
    id: str = ""
    schema: str = ""
    version: str = ""
    operation_id: str = ""
    note: ReplicationNote | None = None


@dataclass
class ReadResult:
    """Read outcome. Public document views are OrderedDict-based; _json stays private."""

    result: Result
    collection: str = ""
    id: str = ""
    _sot: JSONObject | None = field(default=None, repr=False)
    _extra_fields: JSONObject | None = field(default=None, repr=False)
    _cache_summaries: JSONObject | None = field(default=None, repr=False)

    @property
    def sot(self) -> OrderedDict[str, Any] | None:
        return as_ordered_object(self._sot)

    @property
    def extra_fields(self) -> OrderedDict[str, Any] | None:
        return as_ordered_object(self._extra_fields)

    @property
    def cache_summaries(self) -> OrderedDict[str, Any] | None:
        return as_ordered_object(self._cache_summaries)

    def sot_python(self) -> OrderedDict[str, Any]:
        """Ordered public view of SOT (empty if missing)."""
        return self.sot if self.sot is not None else OrderedDict()


@dataclass
class SearchResult:
    result: Result
    collection: str = ""
    search: str = ""
    matches: list[str] = field(default_factory=list)


def write_result_from_envelope(res: Result, *, collection: str = "", doc_id: str = "") -> WriteResult:
    wr = WriteResult(
        result=res,
        collection=collection or res.string_field("collection"),
        id=doc_id or res.string_field("id"),
        schema=res.string_field("$"),
        version=res.string_field("#"),
        operation_id=res.string_field("operationId"),
    )
    versions = res.value_field("versions")
    if isinstance(versions, JSONObject):
        after = versions.get("after")
        if isinstance(after, JSONString):
            wr.version = after.value
        elif isinstance(after, JSONNumber):
            wr.version = after.text
    note_v = res.value_field("note")
    if isinstance(note_v, JSONObject):
        wr.note = _parse_note(note_v)
    return wr


def read_result_from_envelope(res: Result) -> ReadResult:
    sot = res.value_field("sot")
    extra = res.value_field("extraFields")
    cache = res.value_field("cacheSummaries")
    return ReadResult(
        result=res,
        collection=res.string_field("collection"),
        id=res.string_field("id"),
        _sot=sot if isinstance(sot, JSONObject) else None,
        _extra_fields=extra if isinstance(extra, JSONObject) else None,
        _cache_summaries=cache if isinstance(cache, JSONObject) else None,
    )


def search_result_from_envelope(res: Result) -> SearchResult:
    matches_v = res.value_field("matches")
    matches: list[str] = []
    if isinstance(matches_v, JSONArray):
        for item in matches_v.items:
            if isinstance(item, JSONString):
                matches.append(item.value)
    return SearchResult(
        result=res,
        collection=res.string_field("collection"),
        search=res.string_field("search"),
        matches=matches,
    )


def _parse_note(obj: JSONObject) -> ReplicationNote:
    raw = as_ordered(obj)
    note = ReplicationNote(raw=raw if isinstance(raw, OrderedDict) else None)
    code = obj.get("code")
    if isinstance(code, JSONString):
        note.code = code.value
    msg = obj.get("message")
    if isinstance(msg, JSONString):
        note.message = msg.value
    timeout = obj.get("timeoutMs")
    if isinstance(timeout, JSONNumber):
        with contextlib.suppress(ValueError):
            note.timeout_ms = int(timeout.text)
    for attr, key in (
        ("required", "required"),
        ("acknowledged", "acknowledged"),
        ("unacknowledged", "unacknowledged"),
    ):
        v = obj.get(key)
        if isinstance(v, JSONArray):
            setattr(
                note,
                attr,
                [item.value for item in v.items if isinstance(item, JSONString)],
            )
    return note


def content_without_meta(sot: JSONObject) -> JSONObject:
    """Return a clone of SOT without !, $, #."""
    from datorium_client._json.value import clone_value, new_object

    out = new_object()
    for k, v in sot.items_non_void():
        if k in ("!", "$", "#"):
            continue
        out.set(k, clone_value(v))
    return out


def meta_from_sot(sot: JSONObject) -> tuple[str, str, str]:
    """Return (id, schema, version)."""
    doc_id = ""
    schema = ""
    version = ""
    for key, attr in (("!", "id"), ("$", "schema"), ("#", "version")):
        v = sot.get(key)
        if isinstance(v, JSONString):
            if attr == "id":
                doc_id = v.value
            elif attr == "schema":
                schema = v.value
            else:
                version = v.value
        elif isinstance(v, JSONNumber) and attr == "version":
            version = v.text
    return doc_id, schema, version


def is_null_or_void(v: JSONValue | VoidType) -> bool:
    return is_void(v) or isinstance(v, JSONNull)
