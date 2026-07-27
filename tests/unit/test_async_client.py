"""Async client parity smoke tests."""

from __future__ import annotations

import httpx
import pytest

from datorium_client import AsyncClient, Config


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_health_and_establish() -> None:
    establish = {
        "ok": True,
        "general": {"name": "t", "establishmentServer": "serverA", "version": 1},
        "servers": {"serverA": {"baseURL": "http://a.test"}},
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

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok": True, "alive": True})
        return httpx.Response(200, json=establish)

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
