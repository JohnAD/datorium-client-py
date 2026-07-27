"""Resolve direct references inside SOT documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datorium_client._json.value import JSONObject, to_python
from datorium_client.refs import RefKind, parse_ref

if TYPE_CHECKING:
    from datorium_client.client import Client


def resolve_direct_ref(client: Client, ref: str) -> dict[str, Any] | None:
    parsed, ok = parse_ref(ref)
    if not ok or parsed is None or parsed.kind != RefKind.DIRECT:
        return None
    result = client.read(parsed.collection, parsed.id)
    data = result.sot
    return data if isinstance(data, dict) else None


async def aresolve_direct_ref(client: Any, ref: str) -> dict[str, Any] | None:
    parsed, ok = parse_ref(ref)
    if not ok or parsed is None or parsed.kind != RefKind.DIRECT:
        return None
    result = await client.read(parsed.collection, parsed.id)
    data = result.sot
    return data if isinstance(data, dict) else None


def resolve_refs_in_sot(
    client: Client, sot: dict[str, Any] | JSONObject, *, max_depth: int = 1
) -> dict[str, dict[str, Any]]:
    """Resolve top-level direct ref string fields; key is '{collection}/{id}'."""
    data = to_python(sot) if isinstance(sot, JSONObject) else sot
    assert isinstance(data, dict)
    out: dict[str, dict[str, Any]] = {}
    _resolve_level(client, data, out, depth=0, max_depth=max_depth)
    return out


def _resolve_level(
    client: Client,
    data: dict[str, Any],
    out: dict[str, dict[str, Any]],
    *,
    depth: int,
    max_depth: int,
) -> None:
    if depth >= max_depth:
        return
    for _key, value in data.items():
        if not isinstance(value, str):
            continue
        parsed, ok = parse_ref(value)
        if not ok or parsed is None or parsed.kind != RefKind.DIRECT:
            continue
        map_key = f"{parsed.collection}/{parsed.id}"
        if map_key in out:
            continue
        read = client.read(parsed.collection, parsed.id)
        resolved: dict[str, Any] = read.sot or {}
        out[map_key] = resolved
        _resolve_level(client, resolved, out, depth=depth + 1, max_depth=max_depth)
