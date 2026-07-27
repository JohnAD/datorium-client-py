"""Full Todo Compose integration scenario (mirrors datorium-client-go).

Requires env from start_integration_test.sh:

- DATORIUM_TOKEN
- DATORIUM_SERVER1_URL (default http://127.0.0.1:18081)
- DATORIUM_SERVER2_URL (default http://127.0.0.1:18082)
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict

import pytest
from pydantic import BaseModel, ConfigDict, Field

from datorium_client import (
    CODE_DOCUMENT_NOT_FOUND,
    AppError,
    Client,
    Collection,
    Config,
    ReadOptions,
    format_cached,
    format_direct,
    is_app_code,
)
from datorium_client.frontpage import patch_detail_appending_cached_ref, summaries_for_array_field
from datorium_client.resolve import resolve_direct_ref
from datorium_client.searchpath import equals_string_segments
from datorium_client.shard import slot, slot_hex

pytestmark = pytest.mark.integration


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(serialization_alias="displayName", validation_alias="displayName")
    email: str
    todo_lists: list[str] = Field(
        default_factory=list,
        serialization_alias="todoLists",
        validation_alias="todoLists",
    )


class TodoList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    owner: str
    owner_summary: str = Field(serialization_alias="ownerSummary", validation_alias="ownerSummary")


class Todo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    status: str
    list: str
    list_summary: str = Field(serialization_alias="listSummary", validation_alias="listSummary")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _require_live() -> tuple[str, str, str]:
    token = _env("DATORIUM_TOKEN")
    if not token:
        pytest.skip("DATORIUM_TOKEN required (run ./start_integration_test.sh)")
    base1 = _env("DATORIUM_SERVER1_URL", "http://127.0.0.1:18081")
    base2 = _env("DATORIUM_SERVER2_URL", "http://127.0.0.1:18082")
    return token, base1, base2


def _step(name: str) -> None:
    print(f"[{name}]")


def _detail(msg: str) -> None:
    print(f"  {msg}")


def _find_id(start: int, end: int, *exclude: str) -> str:
    excl = set(exclude)
    for i in range(200_000):
        doc_id = f"todo{i:08d}"
        if doc_id in excl:
            continue
        s = slot(doc_id)
        if start <= s <= end:
            return doc_id
    raise RuntimeError(f"no id in range {start:02X}-{end:02X}")


def _wait_ready(client: Client, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = client.ready()
        if res.ok:
            ready = res.value_field("ready")
            from datorium_client._json.value import JSONBoolean

            if isinstance(ready, JSONBoolean) and ready.value:
                return
        time.sleep(0.5)
    raise AssertionError(f"server not ready within {timeout}s")


def _wait_user_front_page_title(
    client: Client,
    user_id: str,
    list_id: str,
    want_title: str,
    *,
    timeout: float = 45.0,
    interval: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        try:
            rr = client.read("Users", user_id, ReadOptions(cache_summaries=True))
            sums = summaries_for_array_field(rr, "todoLists")
            last = f"summaries={sums!r}"
            summary = sums.get("TodoLists", {}).get(list_id)
            if (
                isinstance(summary, dict)
                and summary.get("title") == want_title
                and summary.get("#") not in (None, "")
            ):
                # Prefer matching by document id when present.
                bang = summary.get("!")
                if bang in (None, list_id):
                    return
        except Exception as exc:  # noqa: BLE001 — surface last error in timeout message
            last = str(exc)
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    raise AssertionError(
        f"Users/{user_id} front page missing TodoLists/{list_id} title {want_title!r} "
        f"within {timeout}s (last={last}). If cacheSummaries is empty while todoLists has "
        f"@@ refs, rebuild the Compose image from a datoriumdb checkout that includes "
        f"recursive FindRefFields (array cached refs)"
    )


def _wait_cache_summary(
    client: Client,
    collection: str,
    doc_id: str,
    ref_coll: str,
    ref_id: str,
    field: str,
    want: str,
    *,
    timeout: float = 15.0,
    interval: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        try:
            rr = client.read(collection, doc_id, ReadOptions(cache_summaries=True))
            cache = rr.cache_summaries or {}
            coll = cache.get(ref_coll)
            if isinstance(coll, dict):
                summary = coll.get(ref_id)
                if isinstance(summary, dict):
                    last = repr(summary)
                    if summary.get(field) == want and summary.get("#") not in (None, ""):
                        return
                else:
                    last = f"no summary for {ref_coll}/{ref_id} in {cache!r}"
            else:
                last = f"no cacheSummaries.{ref_coll} (env={cache!r})"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    raise AssertionError(
        f"cache summary {ref_coll}/{ref_id}.{field} != {want!r} within {timeout}s (last={last})"
    )


def _wait_search(
    client: Client,
    collection: str,
    name: str,
    variables: dict[str, str],
    path_segments: list[str],
    want_id: str,
    *,
    timeout: float = 45.0,
) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            sr = client.search(collection, name, variables, path_segments)
            last = ",".join(sr.matches)
            if want_id in sr.matches:
                return
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(0.5)
    raise AssertionError(
        f"search {collection}.{name} missing {want_id} within {timeout}s (last={last})"
    )


@pytest.mark.integration
def test_todo_compose_scenario() -> None:
    token, base1, base2 = _require_live()

    cfg = Config(
        establishment_url=base1,
        token=token,
        base_url_rewrite={
            "server1": base1,
            "server2": base2,
            "http://server1:8080": base1,
            "http://server2:8080": base2,
        },
        wrong_machine_retries=5,
    )

    with Client(cfg) as client:
        _step("WAIT_READY")
        _wait_ready(client)

        _step("ESTABLISH")
        est = client.establish(("Users", 0), ("TodoLists", 0), ("Todos", 0))
        assert est.general.version >= 1
        _detail(f"establishment {est.general.name!r} version {est.general.version}")

        _step("BIND_TYPED")
        users = Collection.of(User, "Users", 0).bind(client)
        todo_lists = Collection.of(TodoList, "TodoLists", 0).bind(client)
        todos = Collection.of(Todo, "Todos", 0).bind(client)
        _detail("bound Users, TodoLists, Todos collection clients")

        _step("PICK_IDS")
        user_low = _find_id(0x00, 0x7F)
        user_high = _find_id(0x80, 0xFF)
        list_low = _find_id(0x00, 0x7F, user_low)
        todo_high = _find_id(0x80, 0xFF, user_high)
        todo_typed = _find_id(0x80, 0xFF, user_high, todo_high)
        _detail(
            f"userLow={user_low}({slot_hex(user_low)}) "
            f"userHigh={user_high}({slot_hex(user_high)}) "
            f"listLow={list_low}({slot_hex(list_low)}) "
            f"todoHigh={todo_high}({slot_hex(todo_high)}) "
            f"todoTyped={todo_typed}({slot_hex(todo_typed)})"
        )

        _step("CREATING_USERS_RAW")
        client.create(
            "Users",
            user_low,
            OrderedDict(
                [
                    ("$", "Users:0"),
                    ("displayName", "Ada"),
                    ("email", "ada@example.com"),
                    ("todoLists", []),
                ]
            ),
        )
        _detail(f"raw Create Users/{user_low} (Ada)")

        _step("CREATING_USERS_TYPED")
        users.create_doc(
            User(display_name="Grace", email="grace@example.com", todo_lists=[]),
            doc_id=user_high,
        )
        _detail(f"typed CreateDoc Users/{user_high} (Grace)")

        _step("CREATING_LIST_TYPED")
        owner_direct = format_direct("Users", user_high)
        owner_cached = format_cached("Users", user_high)
        list_title = "Ship client"
        todo_lists.create_doc(
            TodoList(title=list_title, owner=owner_direct, owner_summary=owner_cached),
            doc_id=list_low,
        )
        _detail(f"typed CreateDoc TodoLists/{list_low} title={list_title!r}")

        _step("LINK_LIST_TO_USER_RAW")
        owner_rr = client.read("Users", user_high)
        assert owner_rr.sot is not None
        client.patch(
            "Users",
            user_high,
            patch_detail_appending_cached_ref(
                str(owner_rr.sot["$"]),
                str(owner_rr.sot["#"]),
                "todoLists",
                "TodoLists",
                list_low,
            ),
        )
        _detail(
            f"raw Patch appended @@__TodoLists__{list_low} onto Users/{user_high}.todoLists"
        )

        _step("READ_USER_FRONT_PAGE")
        _wait_user_front_page_title(client, user_high, list_low, list_title)
        _detail(
            f"raw Read Users/{user_high} with cacheSummaries; todoLists front page shows "
            f"title {list_title!r}"
        )

        _step("PATCH_LIST_TITLE_TYPED")
        list_item = todo_lists.get_doc(list_low)
        updated_list_title = "Ship client v2"
        list_item.doc.title = updated_list_title
        todo_lists.patch_doc(todo_lists.create_patch_from_changes(list_item))
        _detail(
            f"typed CreatePatchFromChanges + PatchDoc TodoLists/{list_low} title → "
            f"{updated_list_title!r}"
        )

        _step("WAIT_FRONT_PAGE_UPDATE")
        _wait_user_front_page_title(
            client, user_high, list_low, updated_list_title, timeout=15.0
        )
        _detail(
            f"re-read Users/{user_high}; cached TodoLists/{list_low}.title now "
            f"{updated_list_title!r}"
        )

        _step("RESOLVE_LIVE_REF")
        list_item = todo_lists.get_doc_opts(list_low, ReadOptions(cache_summaries=True))
        assert list_item.doc.owner == owner_direct
        owner_doc = resolve_direct_ref(client, list_item.doc.owner)
        assert owner_doc is not None
        assert owner_doc.get("displayName") == "Grace"
        _detail("typed GetDocOpts + raw resolve_direct_ref → Grace")

        _step("READ_CACHED_REF")
        seed_rr = client.read("TodoLists", list_low, ReadOptions(cache_summaries=True))
        cache = seed_rr.cache_summaries or {}
        users_cache = cache.get("Users") if isinstance(cache, dict) else None
        if isinstance(users_cache, dict) and user_high in users_cache:
            _detail(
                f"raw seed read TodoLists/{list_low}; Users/{user_high} summary="
                f"{users_cache[user_high]!r}"
            )
        else:
            _detail(f"raw seed read TodoLists/{list_low}; no Users cacheSummaries yet")

        _step("PATCH_CACHED_TARGET_TYPED")
        owner_item = users.get_doc(user_high)
        updated_name = "Grace Hopper"
        owner_patch = users.create_patch(
            owner_item,
            [{"op": "replace", "path": "/displayName", "value": updated_name}],
        )
        users.patch_doc(owner_patch)
        _detail(
            f"typed CreatePatch + PatchDoc Users/{user_high} displayName → {updated_name!r}"
        )

        _step("WAIT_CACHE_UPDATE")
        _wait_cache_summary(
            client,
            "TodoLists",
            list_low,
            "Users",
            user_high,
            "displayName",
            updated_name,
        )
        _detail(
            f"re-read TodoLists/{list_low}; cached Users/{user_high}.displayName now "
            f"{updated_name!r}"
        )

        _step("CREATING_TODO_RAW")
        list_direct = format_direct("TodoLists", list_low)
        list_cached = format_cached("TodoLists", list_low)
        client.create(
            "Todos",
            todo_high,
            OrderedDict(
                [
                    ("$", "Todos:0"),
                    ("title", "Write integration test"),
                    ("status", "open"),
                    ("list", list_direct),
                    ("listSummary", list_cached),
                ]
            ),
        )
        _detail(f"raw Create Todos/{todo_high} status=open")

        _step("PATCHING_TODO_RAW")
        todo_rr = client.read("Todos", todo_high)
        assert todo_rr.sot is not None
        before_ver = str(todo_rr.sot["#"])
        patched = client.patch(
            "Todos",
            todo_high,
            {
                "$": str(todo_rr.sot["$"]),
                "#": before_ver,
                "RFC6902": [{"op": "replace", "path": "/status", "value": "done"}],
            },
        )
        assert patched.version, "expected versions.after after raw patch"
        assert patched.version != before_ver
        todo_rr = client.read("Todos", todo_high, ReadOptions(cache_summaries=True))
        assert todo_rr.sot is not None
        assert todo_rr.sot.get("status") == "done"
        _detail(f"raw Patch status open → done; version {before_ver} → {patched.version}")

        _step("WAIT_SEARCH")
        segs = equals_string_segments("done")
        _wait_search(client, "Todos", "byStatus", {"status": "done"}, segs, todo_high)
        _detail(f"search Todos.byStatus matched {todo_high}")

        _step("DELETING_TODO_RAW")
        assert todo_rr.sot is not None
        try:
            client.delete(
                "Todos",
                todo_high,
                {"$": str(todo_rr.sot["$"]), "#": str(todo_rr.sot["#"])},
            )
        except AppError:
            todo_rr = client.read("Todos", todo_high)
            assert todo_rr.sot is not None
            client.delete(
                "Todos",
                todo_high,
                {"$": str(todo_rr.sot["$"]), "#": str(todo_rr.sot["#"])},
            )
        with pytest.raises(AppError) as exc_info:
            client.read("Todos", todo_high)
        assert is_app_code(exc_info.value, CODE_DOCUMENT_NOT_FOUND)
        _detail("raw Delete confirmed (documentNotFound)")

        _step("TYPED_TODO_CRUD")
        todos.create_doc(
            Todo(
                title="Typed path coverage",
                status="open",
                list=list_direct,
                list_summary=list_cached,
            ),
            doc_id=todo_typed,
        )
        todo_item = todos.get_doc(todo_typed)
        assert todo_item.doc.status == "open"
        assert todo_item.original_doc.status == "open"
        todo_item.doc.status = "done"
        todo_item.original_doc.status = "corrupted"  # must not affect private baseline
        typed_patch = todos.create_patch_from_changes(todo_item)
        typed_patched = todos.patch_doc(typed_patch)
        assert typed_patched.version
        assert typed_patched.version != todo_item.meta.version
        todo_item = todos.get_doc(todo_typed)
        assert todo_item.doc.status == "done"
        try:
            todos.delete_doc(todo_item)
        except AppError:
            todo_item = todos.get_doc(todo_typed)
            todos.delete_doc(todo_item)
        with pytest.raises(AppError) as exc_info:
            todos.get_doc(todo_typed)
        assert is_app_code(exc_info.value, CODE_DOCUMENT_NOT_FOUND)
        _detail(
            f"typed CreateDoc/GetDoc/CreatePatchFromChanges/PatchDoc/DeleteDoc on "
            f"Todos/{todo_typed}"
        )

        _step("PASSED")
        _detail("todo-integration PASSED")
