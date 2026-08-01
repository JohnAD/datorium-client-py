"""Typed collection descriptors and bound clients."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, overload

from datorium_client._json.value import JSONObject, from_python, new_object, new_string
from datorium_client._patch.patch import Patch, apply_patch, diff, parse_patch, patch_to_json_value
from datorium_client._schema.apply import apply_schema
from datorium_client._schema.compile import CompiledSchema, compile_schema
from datorium_client.async_client import AsyncClient
from datorium_client.client import Client
from datorium_client.command import ensure_operation_id_object
from datorium_client.crud import (
    ReadOptions,
    ReadResult,
    WriteResult,
    content_without_meta,
    meta_from_sot,
)
from datorium_client.ids import new_document_id, new_operation_id
from datorium_client.ordered import Void, as_ordered_object
from datorium_client.schema_compat import (
    check_model_schema_compatible,
    datorium_ref_formats,
    model_to_ordered_object,
    python_from_sot,
)

T = TypeVar("T")

_META_KEYS = frozenset({"$", "#", "!", "operationId"})


def _merge_extra_fields(detail: JSONObject, extra_fields: Mapping[str, Any]) -> None:
    """Append non-schema extras onto a create/patch detail object (insertion order)."""
    for key, value in extra_fields.items():
        if not isinstance(key, str):
            raise TypeError("extra_fields keys must be strings")
        if key in _META_KEYS:
            raise ValueError(f"extra_fields must not include meta key {key!r}")
        if detail.has(key):
            raise ValueError(f"extra_fields key {key!r} conflicts with document field")
        if value is Void:
            continue
        detail.set(key, from_python(value))


@dataclass(frozen=True)
class DocMeta:
    id: str
    schema: str
    version: str


@dataclass
class CollectionItem(Generic[T]):
    doc: T
    original_doc: T
    meta: DocMeta
    result: ReadResult
    _original_content: JSONObject = field(repr=False)
    _binding: object = field(repr=False)
    _extra_fields: JSONObject | None = field(default=None, repr=False)
    _cache_summaries: JSONObject | None = field(default=None, repr=False)

    @property
    def extra_fields(self) -> OrderedDict[str, Any] | None:
        return as_ordered_object(self._extra_fields)

    @property
    def cache_summaries(self) -> OrderedDict[str, Any] | None:
        return as_ordered_object(self._cache_summaries)


@dataclass
class CollectionPatch(Generic[T]):
    patch: Patch
    _id: str
    _version: str
    _marker: str
    _binding: object

    def id(self) -> str:
        return self._id

    def version(self) -> str:
        return self._version


class Collection(Generic[T]):
    def __init__(self, name: str, version: int, model_type: type[T]) -> None:
        if not name:
            raise ValueError("collection name required")
        if version < 0:
            raise ValueError("schema version must be >= 0")
        self.name = name
        self.version = version
        self.model_type = model_type

    @classmethod
    def of(cls, model_type: type[T], name: str, version: int) -> Collection[T]:
        return cls(name, version, model_type)

    def collection_name(self) -> str:
        return self.name

    def schema_version(self) -> int:
        return self.version

    def schema_marker(self) -> str:
        return f"{self.name}:{self.version}"

    def bind(self, client: Client) -> CollectionClient[T]:
        est = client.cached_establishment()
        if est is None:
            est = client.establish((self.name, self.version))
        entry = est.schemas.get(self.name)
        if entry is None:
            raise ValueError(f"collection {self.name!r} not in establishment schemas")
        if entry.version != self.version:
            raise ValueError(
                f"schema version mismatch for {self.name}: "
                f"local={self.version} server={entry.version}"
            )
        compiled = compile_schema(entry.schema, formats=datorium_ref_formats())
        check_model_schema_compatible(self.model_type, compiled)
        return CollectionClient(self, client, compiled, binding=object())

    async def bind_async(self, client: AsyncClient) -> AsyncCollectionClient[T]:
        est = client.cached_establishment()
        if est is None:
            est = await client.establish((self.name, self.version))
        entry = est.schemas.get(self.name)
        if entry is None:
            raise ValueError(f"collection {self.name!r} not in establishment schemas")
        if entry.version != self.version:
            raise ValueError(
                f"schema version mismatch for {self.name}: "
                f"local={self.version} server={entry.version}"
            )
        compiled = compile_schema(entry.schema, formats=datorium_ref_formats())
        check_model_schema_compatible(self.model_type, compiled)
        return AsyncCollectionClient(self, client, compiled, binding=object())


class CollectionClient(Generic[T]):
    def __init__(
        self,
        collection: Collection[T],
        client: Client,
        compiled: CompiledSchema,
        *,
        binding: object,
    ) -> None:
        self._collection = collection
        self._client = client
        self._compiled = compiled
        self._binding = binding

    def client(self) -> Client:
        return self._client

    def collection(self) -> Collection[T]:
        return self._collection

    def compiled_schema(self) -> CompiledSchema:
        return self._compiled

    def create_doc(
        self,
        doc: T,
        doc_id: str | None = None,
        *,
        extra_fields: Mapping[str, Any] | None = None,
    ) -> WriteResult:
        if doc_id is not None and doc_id == "":
            raise ValueError("empty document id rejected")
        if doc_id is None:
            doc_id = new_document_id()
        detail = model_to_ordered_object(doc, schema_marker=self._collection.schema_marker())
        if extra_fields:
            _merge_extra_fields(detail, extra_fields)
        apply_schema(detail, self._compiled)
        ensure_operation_id_object(detail)
        return self._client.create_ordered(self._collection.name, doc_id, detail)

    def get_doc(self, doc_id: str) -> CollectionItem[T]:
        return self.get_doc_opts(doc_id, None)

    def get_doc_opts(self, doc_id: str, opts: ReadOptions | None) -> CollectionItem[T]:
        result = self._client.read(self._collection.name, doc_id, opts)
        return self._item_from_read(result)

    @overload
    def delete_doc(self, item: CollectionItem[T], /) -> WriteResult: ...

    @overload
    def delete_doc(self, doc_id: str, version: str, /) -> WriteResult: ...

    def delete_doc(
        self, item: CollectionItem[T] | str, version: str | None = None, /
    ) -> WriteResult:
        if isinstance(item, str):
            if version is None:
                raise TypeError("version is required when deleting by document id")
            return self._delete(item, version)
        self._check_binding(item._binding)
        if not item.meta.id or not item.meta.version:
            raise ValueError("item missing id or version")
        return self._delete(item.meta.id, item.meta.version)

    def _delete(self, doc_id: str, version: str) -> WriteResult:
        detail = {
            "$": self._collection.schema_marker(),
            "#": version,
            "operationId": new_operation_id(),
        }
        return self._client.delete(self._collection.name, doc_id, detail)

    def create_patch_from_changes(self, item: CollectionItem[T]) -> CollectionPatch[T]:
        self._check_binding(item._binding)
        current = model_to_ordered_object(item.doc)
        # Normalize both with schema before diff
        before = apply_schema(item._original_content, self._compiled)
        after = apply_schema(current, self._compiled)
        patch = diff(before, after, schema=None)
        if len(patch) == 0:
            raise ValueError("no changes to patch")
        apply_patch(before, patch, schema=self._compiled)
        return CollectionPatch(
            patch=patch,
            _id=item.meta.id,
            _version=item.meta.version,
            _marker=self._collection.schema_marker(),
            _binding=self._binding,
        )

    def create_patch(self, item: CollectionItem[T], patch: Patch | list[Any] | str) -> CollectionPatch[T]:
        self._check_binding(item._binding)
        if not isinstance(patch, Patch):
            patch = parse_patch(patch)
        apply_patch(item._original_content, patch, schema=self._compiled)
        return CollectionPatch(
            patch=patch,
            _id=item.meta.id,
            _version=item.meta.version,
            _marker=self._collection.schema_marker(),
            _binding=self._binding,
        )

    def patch_doc(self, patch: CollectionPatch[T]) -> WriteResult:
        self._check_binding(patch._binding)
        detail = new_object()
        detail.set("$", new_string(patch._marker))
        detail.set("#", new_string(patch._version))
        detail.set("RFC6902", patch_to_json_value(patch.patch))
        detail.set("operationId", new_string(new_operation_id()))
        return self._client.patch_ordered(self._collection.name, patch._id, detail)

    def _item_from_read(self, result: ReadResult) -> CollectionItem[T]:
        if result._sot is None:
            raise ValueError("read result missing sot")
        doc_id, schema, version = meta_from_sot(result._sot)
        original = content_without_meta(result._sot)
        model = python_from_sot(self._collection.model_type, result._sot)
        # Keep a second instance as original snapshot
        original_model = python_from_sot(self._collection.model_type, result._sot)
        return CollectionItem(
            doc=model,
            original_doc=original_model,
            meta=DocMeta(id=doc_id or result.id, schema=schema, version=version),
            result=result,
            _original_content=original,
            _binding=self._binding,
            _extra_fields=result._extra_fields,
            _cache_summaries=result._cache_summaries,
        )

    def _check_binding(self, binding: object) -> None:
        if binding is not self._binding:
            raise ValueError("collection item/patch binding mismatch")


class AsyncCollectionClient(Generic[T]):
    def __init__(
        self,
        collection: Collection[T],
        client: AsyncClient,
        compiled: CompiledSchema,
        *,
        binding: object,
    ) -> None:
        self._collection = collection
        self._client = client
        self._compiled = compiled
        self._binding = binding

    def collection(self) -> Collection[T]:
        return self._collection

    async def create_doc(
        self,
        doc: T,
        doc_id: str | None = None,
        *,
        extra_fields: Mapping[str, Any] | None = None,
    ) -> WriteResult:
        if doc_id is not None and doc_id == "":
            raise ValueError("empty document id rejected")
        if doc_id is None:
            doc_id = new_document_id()
        detail = model_to_ordered_object(doc, schema_marker=self._collection.schema_marker())
        if extra_fields:
            _merge_extra_fields(detail, extra_fields)
        apply_schema(detail, self._compiled)
        ensure_operation_id_object(detail)
        return await self._client.create_ordered(self._collection.name, doc_id, detail)

    async def get_doc(self, doc_id: str) -> CollectionItem[T]:
        return await self.get_doc_opts(doc_id, None)

    async def get_doc_opts(self, doc_id: str, opts: ReadOptions | None) -> CollectionItem[T]:
        result = await self._client.read(self._collection.name, doc_id, opts)
        return self._item_from_read(result)

    @overload
    async def delete_doc(self, item: CollectionItem[T], /) -> WriteResult: ...

    @overload
    async def delete_doc(self, doc_id: str, version: str, /) -> WriteResult: ...

    async def delete_doc(
        self, item: CollectionItem[T] | str, version: str | None = None, /
    ) -> WriteResult:
        if isinstance(item, str):
            if version is None:
                raise TypeError("version is required when deleting by document id")
            return await self._delete(item, version)
        if item._binding is not self._binding:
            raise ValueError("collection item/patch binding mismatch")
        if not item.meta.id or not item.meta.version:
            raise ValueError("item missing id or version")
        return await self._delete(item.meta.id, item.meta.version)

    async def _delete(self, doc_id: str, version: str) -> WriteResult:
        detail = {
            "$": self._collection.schema_marker(),
            "#": version,
            "operationId": new_operation_id(),
        }
        return await self._client.delete(self._collection.name, doc_id, detail)

    def create_patch_from_changes(self, item: CollectionItem[T]) -> CollectionPatch[T]:
        if item._binding is not self._binding:
            raise ValueError("collection item/patch binding mismatch")
        current = model_to_ordered_object(item.doc)
        before = apply_schema(item._original_content, self._compiled)
        after = apply_schema(current, self._compiled)
        patch = diff(before, after)
        if len(patch) == 0:
            raise ValueError("no changes to patch")
        apply_patch(before, patch, schema=self._compiled)
        return CollectionPatch(
            patch=patch,
            _id=item.meta.id,
            _version=item.meta.version,
            _marker=self._collection.schema_marker(),
            _binding=self._binding,
        )

    def create_patch(self, item: CollectionItem[T], patch: Patch | list[Any] | str) -> CollectionPatch[T]:
        if item._binding is not self._binding:
            raise ValueError("collection item/patch binding mismatch")
        if not isinstance(patch, Patch):
            patch = parse_patch(patch)
        apply_patch(item._original_content, patch, schema=self._compiled)
        return CollectionPatch(
            patch=patch,
            _id=item.meta.id,
            _version=item.meta.version,
            _marker=self._collection.schema_marker(),
            _binding=self._binding,
        )

    async def patch_doc(self, patch: CollectionPatch[T]) -> WriteResult:
        if patch._binding is not self._binding:
            raise ValueError("collection item/patch binding mismatch")
        detail = new_object()
        detail.set("$", new_string(patch._marker))
        detail.set("#", new_string(patch._version))
        detail.set("RFC6902", patch_to_json_value(patch.patch))
        detail.set("operationId", new_string(new_operation_id()))
        return await self._client.patch_ordered(self._collection.name, patch._id, detail)

    def _item_from_read(self, result: ReadResult) -> CollectionItem[T]:
        if result._sot is None:
            raise ValueError("read result missing sot")
        doc_id, schema, version = meta_from_sot(result._sot)
        original = content_without_meta(result._sot)
        model = python_from_sot(self._collection.model_type, result._sot)
        original_model = python_from_sot(self._collection.model_type, result._sot)
        return CollectionItem(
            doc=model,
            original_doc=original_model,
            meta=DocMeta(id=doc_id or result.id, schema=schema, version=version),
            result=result,
            _original_content=original,
            _binding=self._binding,
            _extra_fields=result._extra_fields,
            _cache_summaries=result._cache_summaries,
        )


def must_collection(model_type: type[T], name: str, version: int) -> Collection[T]:
    return Collection.of(model_type, name, version)
