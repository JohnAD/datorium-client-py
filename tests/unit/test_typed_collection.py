"""Typed collection binding and patch tests."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from pydantic import BaseModel, Field

from datorium_client import Client, Config
from datorium_client.collection import Collection
from datorium_client.schema_compat import SchemaCompatibilityError

ESTABLISH = {
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


class TodoModel(BaseModel):
    title: str
    status: str


@dataclass
class TodoDC:
    title: str
    status: str


@pytest.mark.unit
def test_bind_pydantic_and_create() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/establish"):
            return httpx.Response(200, json=ESTABLISH)
        body = request.content.decode()
        assert "create Todos" in body
        assert '"title":"Buy milk"' in body or '"title": "Buy milk"' in body.replace(" ", "")
        return httpx.Response(
            200,
            json={
                "ok": True,
                "collection": "Todos",
                "id": "todo1",
                "$": "Todos:0",
                "#": "ver1",
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    # bind auto-establishes; no explicit client.establish() required
    col = Collection.of(TodoModel, "Todos", 0).bind(client)
    wr = col.create_doc(TodoModel(title="Buy milk", status="open"), doc_id="todo1")
    assert wr.version == "ver1"


@pytest.mark.unit
def test_bind_dataclass() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ESTABLISH)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    Collection.of(TodoDC, "Todos", 0).bind(client)


@pytest.mark.unit
def test_schema_shape_mismatch() -> None:
    class Bad(BaseModel):
        status: str
        title: str  # wrong order

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ESTABLISH)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    client.establish(("Todos", 0))
    with pytest.raises(SchemaCompatibilityError):
        Collection.of(Bad, "Todos", 0).bind(client)


@pytest.mark.unit
def test_create_doc_extra_fields() -> None:
    from collections import OrderedDict

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/establish"):
            return httpx.Response(200, json=ESTABLISH)
        body = request.content.decode()
        assert "create Todos" in body
        assert '"source":"mobile"' in body.replace(" ", "") or '"source": "mobile"' in body
        assert '"priority":1' in body.replace(" ", "") or '"priority": 1' in body
        return httpx.Response(
            200,
            json={
                "ok": True,
                "collection": "Todos",
                "id": "todo1",
                "$": "Todos:0",
                "#": "ver1",
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    client.establish(("Todos", 0))
    col = Collection.of(TodoModel, "Todos", 0).bind(client)
    wr = col.create_doc(
        TodoModel(title="Buy milk", status="open"),
        doc_id="todo1",
        extra_fields=OrderedDict([("source", "mobile"), ("priority", 1)]),
    )
    assert wr.id == "todo1"


@pytest.mark.unit
def test_create_doc_extra_fields_conflict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ESTABLISH)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    client.establish(("Todos", 0))
    col = Collection.of(TodoModel, "Todos", 0).bind(client)
    with pytest.raises(ValueError, match="conflicts"):
        col.create_doc(
            TodoModel(title="Buy milk", status="open"),
            extra_fields={"title": "other"},
        )


@pytest.mark.unit
def test_delete_doc_by_id_and_version() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/establish"):
            return httpx.Response(200, json=ESTABLISH)
        body = request.content.decode()
        seen.append(body)
        assert "delete Todos todo1" in body
        assert '"#":"ver1"' in body.replace(" ", "") or '"#": "ver1"' in body
        return httpx.Response(
            200,
            json={"ok": True, "collection": "Todos", "id": "todo1", "#": "ver2"},
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    client.establish(("Todos", 0))
    col = Collection.of(TodoModel, "Todos", 0).bind(client)
    wr = col.delete_doc("todo1", "ver1")
    assert wr.id == "todo1"
    assert seen


@pytest.mark.unit
def test_alias_wire_names() -> None:
    class Aliased(BaseModel):
        title: str = Field(serialization_alias="title")
        status: str = Field(serialization_alias="status")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ESTABLISH)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Client(Config(establishment_url="http://a.test", token="t", http_client=http))
    client.establish(("Todos", 0))
    Collection.of(Aliased, "Todos", 0).bind(client)
