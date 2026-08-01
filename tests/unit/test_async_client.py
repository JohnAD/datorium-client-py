"""Async client parity smoke tests."""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from datorium_client import AsyncClient, Config
from datorium_client.collection import Collection

ESTABLISH_STALE = {
    "ok": True,
    "general": {"name": "t", "establishmentServer": "serverA", "version": 1},
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
    "schemas": {},
}

ESTABLISH_FRESH = {
    **ESTABLISH_STALE,
    "general": {**ESTABLISH_STALE["general"], "version": 2},
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
@pytest.mark.asyncio
async def test_async_health_and_establish() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok": True, "alive": True})
        return httpx.Response(200, json=ESTABLISH_STALE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = AsyncClient(
            Config(establishment_url="http://a.test", token="t"),
            http_client=http,
        )
        health = await client.health()
        assert health.ok is True
        est = await client.establish()
        assert est.general.version == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_wrong_machine_reestablishes() -> None:
    establish_count = {"n": 0}
    calls: list[str] = []

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
                    "command": "create",
                    "collection": "Todos",
                    "id": "async1",
                    "configVersion": 1,
                    "errors": [{"code": "wrongMachine", "message": "bounce"}],
                },
            )
        return httpx.Response(
            200,
            json={"ok": True, "collection": "Todos", "id": "async1", "$": "Todos:0", "#": "v1"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncClient(
            Config(establishment_url="http://a.test", token="t"),
            http_client=http,
        )
        wr = await client.create(
            "Todos",
            "async1",
            {"$": "Todos:0", "title": "t", "status": "open"},
        )
        assert wr.id == "async1"
        assert any("b.test" in c and c.endswith("/command") for c in calls)
        assert establish_count["n"] >= 2


ESTABLISH_TODOS = {
    **ESTABLISH_STALE,
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bind_async_auto_establishes() -> None:
    class Todo(BaseModel):
        title: str
        status: str

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ESTABLISH_TODOS)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = AsyncClient(
            Config(establishment_url="http://a.test", token="t"),
            http_client=http,
        )
        todos = await Collection.of(Todo, "Todos", 0).bind_async(client)
        assert todos.collection().name == "Todos"
        assert client.cached_establishment() is not None
