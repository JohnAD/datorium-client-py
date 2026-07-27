"""Front-page / cached-reference helpers."""

from __future__ import annotations

from typing import Any

from datorium_client._json.value import JSONArray, JSONNull, JSONObject, JSONString, is_void
from datorium_client.crud import ReadResult
from datorium_client.ordered import as_ordered
from datorium_client.refs import RefKind, format_cached, parse_ref


def append_cached_ref_op(array_field: str, collection: str, doc_id: str) -> dict[str, Any]:
    from datorium_client._patch.pointer import escape

    return {
        "op": "add",
        "path": f"/{escape(array_field)}/-",
        "value": format_cached(collection, doc_id),
    }


def patch_detail_appending_cached_ref(
    schema_marker: str,
    version: str,
    array_field: str,
    ref_collection: str,
    ref_id: str,
) -> dict[str, Any]:
    return {
        "$": schema_marker,
        "#": version,
        "RFC6902": [append_cached_ref_op(array_field, ref_collection, ref_id)],
    }


def summaries_for_array_field(read: ReadResult, array_field: str) -> dict[str, dict[str, Any]]:
    """Map collection -> id -> summary object for @@ refs in a SOT array field."""
    out: dict[str, dict[str, Any]] = {}
    if read._sot is None or read._cache_summaries is None:
        return out
    arr = read._sot.get(array_field)
    if not isinstance(arr, JSONArray):
        return out
    cache = read._cache_summaries
    for item in arr.items:
        if not isinstance(item, JSONString):
            continue
        ref, ok = parse_ref(item.value)
        if not ok or ref is None or ref.kind != RefKind.CACHED:
            continue
        coll_obj = cache.get(ref.collection)
        if not isinstance(coll_obj, JSONObject):
            continue
        summary = coll_obj.get(ref.id)
        if isinstance(summary, JSONObject):
            ver = summary.get("#")
            if is_void(ver) or isinstance(ver, JSONNull):
                continue
            converted = as_ordered(summary)
            if isinstance(converted, dict):
                out.setdefault(ref.collection, {})[ref.id] = converted
    return out
