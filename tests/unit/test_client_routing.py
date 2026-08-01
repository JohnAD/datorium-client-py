"""Client routing and command tests with MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from datorium_client import AppError, Client, Config, is_app_code
from datorium_client.command import build_command
from datorium_client.crud import write_result_from_envelope
from datorium_client.envelope import decode_result
from datorium_client.searchpath import equals_string_segments

ESTABLISH_STALE = {
    "ok": True,
    "general": {
        "name": "test",
        "establishmentServer": "serverA",
        "version": 1,
    },
    "servers": {
        "serverA": {"baseURL": "http://a.test"},
        "serverB": {"baseURL": "http://b.test"},
    },
    "shardMap": {
        "default": {
            "00-FF": {
                "SHARD_SOT_MEMBER": "serverA",
                "SHARD_READ_MEMBER": ["serverA"],
                "PROXY_READ_MEMBER": [],
            }
        }
    },
    "schemas": {
        "Todos": {
            "version": 0,
            "schema": {
                "kind": "object",
                "children": [
                    {"name": "title", "kind": "string", "required": True},
                    {"name": "status", "kind": "string", "required": True},
                ],
            },
        }
    },
}

ESTABLISH_FRESH = {
    **ESTABLISH_STALE,
    "general": {
        **ESTABLISH_STALE["general"],
        "version": 2,
    },
    "shardMap": {
        "default": {
            "00-FF": {
                "SHARD_SOT_MEMBER": "serverB",
                "SHARD_READ_MEMBER": ["serverB"],
                "PROXY_READ_MEMBER": [],
            }
        }
    },
}


@pytest.mark.unit
def test_wrong_machine_refreshes_establishment_and_ignores_hints() -> None:
    calls: list[str] = []
    establish_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/establish"):
            establish_count["n"] += 1
            # First fetch is stale (SOT=A). After wrongMachine, always refresh;
            # return fresh topology (SOT=B). Hints must not be required or trusted.
            if establish_count["n"] == 1:
                return httpx.Response(200, json=ESTABLISH_STALE)
            return httpx.Response(200, json=ESTABLISH_FRESH)
        if request.url.host == "a.test":
            return httpx.Response(
                200,
                json={
                    "ok": False,
                    "command": "create",
                    "collection": "Todos",
                    "id": "01ABCDEFGHJKLMNPQRSTVWXYZ0",
                    "configVersion": 1,
                    "errors": [{"code": "wrongMachine", "message": "bounce"}],
                },
            )
        return httpx.Response(
            200,
            json={"ok": True, "collection": "Todos", "id": "x", "$": "Todos:0", "#": "v1"},
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="tok", http_client=http))
    wr = client.create(
        "Todos",
        "01ABCDEFGHJKLMNPQRSTVWXYZ0",
        {"$": "Todos:0", "title": "t", "status": "open"},
    )
    assert wr.id == "01ABCDEFGHJKLMNPQRSTVWXYZ0"
    assert any("b.test" in c and c.endswith("/command") for c in calls)
    assert establish_count["n"] >= 2


@pytest.mark.unit
def test_search_wrong_machine_reestablishes_and_reroutes() -> None:
    calls: list[str] = []
    establish_count = {"n": 0}
    segs = equals_string_segments("done")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/establish"):
            establish_count["n"] += 1
            if establish_count["n"] == 1:
                return httpx.Response(200, json=ESTABLISH_STALE)
            return httpx.Response(200, json=ESTABLISH_FRESH)
        if request.url.host == "a.test":
            return httpx.Response(
                200,
                json={
                    "ok": False,
                    "command": "search",
                    "collection": "Todos",
                    "search": "byStatus",
                    "configVersion": 1,
                    "errors": [{"code": "wrongMachine", "message": "bounce"}],
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "collection": "Todos",
                "search": "byStatus",
                "matches": ["todo1"],
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="tok", http_client=http))
    client.establish()
    sr = client.search("Todos", "byStatus", {"status": "done"}, segs)
    assert sr.matches == ["todo1"]
    assert any("b.test" in c and c.endswith("/command") for c in calls)
    assert establish_count["n"] >= 2


@pytest.mark.unit
def test_patch_write_result_version_before() -> None:
    body = json.dumps(
        {
            "ok": True,
            "collection": "Todos",
            "id": "todo1",
            "$": "Todos:0",
            "operationId": "op1",
            "versions": {"before": "ver1", "after": "ver2"},
        }
    ).encode()
    wr = write_result_from_envelope(decode_result(body), collection="Todos", doc_id="todo1")
    assert wr.version_before == "ver1"
    assert wr.version == "ver2"


@pytest.mark.unit
def test_command_marshaled_once_format() -> None:
    line = build_command("create", "Todos", "id1", {"title": "a", "status": "open"})
    assert line.startswith("create Todos id1 {")
    detail = line.split(" ", 3)[3]
    parsed = json.loads(detail)
    assert parsed["title"] == "a"


@pytest.mark.unit
def test_app_error_on_ok_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/establish"):
            return httpx.Response(200, json=ESTABLISH_STALE)
        return httpx.Response(
            200,
            json={
                "ok": False,
                "errors": [{"code": "documentNotFound", "message": "missing"}],
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="tok", http_client=http))
    with pytest.raises(AppError) as ei:
        client.read("Todos", "missing")
    assert is_app_code(ei.value, "documentNotFound")
