"""Client routing and command tests with MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from datorium_client import AppError, Client, Config, is_app_code
from datorium_client.command import build_command

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
            # return fresh topology (SOT=B). Hints pointing elsewhere must be ignored.
            if establish_count["n"] == 1:
                return httpx.Response(200, json=ESTABLISH_STALE)
            return httpx.Response(200, json=ESTABLISH_FRESH)
        if request.url.host == "a.test":
            return httpx.Response(
                200,
                json={
                    "ok": False,
                    "errors": [{"code": "wrongMachine", "message": "bounce"}],
                    # Untrusted / soon-to-be-removed bounce hints:
                    "correctServer": "serverA",
                    "baseURL": "http://a.test",
                    "configVersion": 1,
                    "shardSlot": "00",
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
