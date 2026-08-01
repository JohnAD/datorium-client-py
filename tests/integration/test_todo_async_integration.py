"""Focused AsyncClient / bind_async CRUD against the live Compose stack.

Requires the same env as start_integration_test.sh (DATORIUM_TOKEN and server URLs).
Does not re-run the full cache/search story — see test_todo_integration.py.
"""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel, ConfigDict, Field

from datorium_client import (
    CODE_DOCUMENT_NOT_FOUND,
    AppError,
    AsyncClient,
    Collection,
    Config,
    format_cached,
    format_direct,
    is_app_code,
)
from datorium_client.shard import slot

pytestmark = pytest.mark.integration


class Todo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    status: str
    list: str
    list_summary: str = Field(serialization_alias="listSummary", validation_alias="listSummary")


def _require_live() -> tuple[str, str, str]:
    token = os.environ.get("DATORIUM_TOKEN", "")
    if not token:
        pytest.skip("DATORIUM_TOKEN required (run ./start_integration_test.sh)")
    base1 = os.environ.get("DATORIUM_SERVER1_URL", "http://127.0.0.1:18081")
    base2 = os.environ.get("DATORIUM_SERVER2_URL", "http://127.0.0.1:18082")
    return token, base1, base2


def _find_id(start: int, end: int, *exclude: str) -> str:
    excl = set(exclude)
    for i in range(200_000):
        doc_id = f"async{i:08d}"
        if doc_id in excl:
            continue
        s = slot(doc_id)
        if start <= s <= end:
            return doc_id
    raise RuntimeError(f"no id in range {start:02X}-{end:02X}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_typed_todo_crud() -> None:
    token, base1, base2 = _require_live()
    cfg = Config(
        establishment_url=base1,
        token=token,
        collections=[("Users", 0), ("TodoLists", 0), ("Todos", 0)],
        base_url_rewrite={
            "server1": base1,
            "server2": base2,
            "http://server1:8080": base1,
            "http://server2:8080": base2,
        },
        wrong_machine_retries=5,
    )

    async with AsyncClient(cfg) as client:
        todos = await Collection.of(Todo, "Todos", 0).bind_async(client)

        list_id = _find_id(0x00, 0x7F)
        user_id = _find_id(0x80, 0xFF)
        todo_id = _find_id(0x80, 0xFF, user_id)

        await client.create(
            "Users",
            user_id,
            {
                "$": "Users:0",
                "displayName": "Async User",
                "email": "async@example.com",
                "todoLists": [],
            },
        )
        await client.create(
            "TodoLists",
            list_id,
            {
                "$": "TodoLists:0",
                "title": "Async list",
                "owner": format_direct("Users", user_id),
                "ownerSummary": format_cached("Users", user_id),
            },
        )

        list_direct = format_direct("TodoLists", list_id)
        list_cached = format_cached("TodoLists", list_id)
        await todos.create_doc(
            Todo(
                title="Async typed coverage",
                status="open",
                list=list_direct,
                list_summary=list_cached,
            ),
            doc_id=todo_id,
        )
        item = await todos.get_doc(todo_id)
        assert item.doc.status == "open"
        item.doc.status = "done"
        patch = todos.create_patch_from_changes(item)
        patched = await todos.patch_doc(patch)
        assert patched.version
        assert patched.version_before == item.meta.version
        item = await todos.get_doc(todo_id)
        assert item.doc.status == "done"
        await todos.delete_doc(item)
        with pytest.raises(AppError) as exc_info:
            await todos.get_doc(todo_id)
        assert is_app_code(exc_info.value, CODE_DOCUMENT_NOT_FOUND)
