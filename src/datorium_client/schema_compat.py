"""Strict shape compatibility between Python models and Datorium schemas."""

from __future__ import annotations

import dataclasses
from dataclasses import is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter
from pydantic.fields import FieldInfo

from datorium_client._json.value import JSONObject
from datorium_client._schema.compile import CompiledSchema, SchemaEntry


class SchemaCompatibilityError(ValueError):
    def __init__(self, mismatches: list[str]) -> None:
        self.mismatches = mismatches
        super().__init__("schema compatibility failed:\n- " + "\n- ".join(mismatches))


def check_model_schema_compatible(model_type: type[Any], compiled: CompiledSchema) -> None:
    shape = _model_shape(model_type)
    mismatches: list[str] = []
    _compare_shape(shape, compiled.root, path="$", mismatches=mismatches)
    if mismatches:
        raise SchemaCompatibilityError(mismatches)


def _model_shape(model_type: type[Any]) -> dict[str, Any]:
    """Return ordered {wire_name: python_annotation} for object models."""
    if issubclass(model_type, BaseModel):
        fields: dict[str, Any] = {}
        for name, finfo in model_type.model_fields.items():
            wire = _pydantic_wire_name(name, finfo)
            fields[wire] = finfo.annotation
        return {"kind": "object", "fields": fields, "required": _pydantic_required(model_type)}
    if is_dataclass(model_type):
        hints = get_type_hints(model_type, include_extras=True)
        fields = {}
        required: set[str] = set()
        for f in dataclasses.fields(model_type):
            wire = _dataclass_wire_name(f)
            fields[wire] = hints.get(f.name, f.type)
            if (
                f.default is dataclasses.MISSING
                and f.default_factory is dataclasses.MISSING
            ):
                required.add(wire)
        return {"kind": "object", "fields": fields, "required": required}
    # Fallback via TypeAdapter JSON schema-ish: treat as object with no fields
    TypeAdapter(model_type)
    raise SchemaCompatibilityError(
        [f"unsupported model type {model_type!r}; use BaseModel or dataclass"]
    )


def _pydantic_wire_name(name: str, finfo: FieldInfo) -> str:
    if finfo.serialization_alias:
        return str(finfo.serialization_alias)
    if finfo.alias:
        return str(finfo.alias)
    return name


def _pydantic_required(model_type: type[BaseModel]) -> set[str]:
    req: set[str] = set()
    for name, finfo in model_type.model_fields.items():
        wire = _pydantic_wire_name(name, finfo)
        if finfo.is_required():
            req.add(wire)
    return req


def _dataclass_wire_name(f: dataclasses.Field[Any]) -> str:
    meta = f.metadata
    if meta:
        for item in meta:
            if isinstance(item, dict) and "wire" in item:
                return str(item["wire"])
            if isinstance(item, dict) and "alias" in item:
                return str(item["alias"])
    return f.name


def _compare_shape(
    shape: dict[str, Any],
    entry: SchemaEntry,
    *,
    path: str,
    mismatches: list[str],
) -> None:
    if entry.kind != "object":
        mismatches.append(f"{path}: server kind is {entry.kind}, model is object")
        return
    model_fields: dict[str, Any] = shape["fields"]
    model_names = list(model_fields.keys())
    server_names = [c.name for c in entry.children]
    # Strict shape-only: exact ordered child names must match model field order.
    if model_names != server_names:
        mismatches.append(
            f"{path}: field order/names mismatch: model={model_names} server={server_names}"
        )
        return
    for child in entry.children:
        ann = model_fields[child.name]
        _compare_annotation(ann, child, path=f"{path}.{child.name}", mismatches=mismatches)
        model_req = child.name in shape["required"]
        if child.required and not model_req and not child.has_default:
            mismatches.append(f"{path}.{child.name}: required on server but optional on model")
        if model_req and not child.required and not child.has_default:
            # optional server field required on model is ok
            pass


def _compare_annotation(
    ann: Any, entry: SchemaEntry, *, path: str, mismatches: list[str]
) -> None:
    ann, nullable = _strip_optional(ann)
    if nullable and not entry.nullable and entry.kind != "null":
        mismatches.append(f"{path}: model allows null but server field is not nullable")
    if entry.nullable and not nullable and entry.kind != "null":
        # model non-optional while server nullable — allowed (stricter client)
        pass

    origin = get_origin(ann)
    if entry.kind == "object":
        if not (
            isinstance(ann, type)
            and (is_dataclass(ann) or issubclass(ann, BaseModel))
        ):
            mismatches.append(f"{path}: expected nested object model, got {ann!r}")
            return
        nested = _model_shape(ann)
        _compare_shape(nested, entry, path=path, mismatches=mismatches)
        return
    if entry.kind == "array":
        if origin not in (list, list[Any]):
            # list[...]
            if origin is not list:
                mismatches.append(f"{path}: expected list, got {ann!r}")
                return
        args = get_args(ann)
        item_ann = args[0] if args else Any
        if entry.items is not None:
            _compare_annotation(item_ann, entry.items, path=f"{path}[]", mismatches=mismatches)
        return
    expected = {
        "string": str,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }.get(entry.kind)
    if expected is None:
        return
    if entry.kind == "number":
        if ann not in (int, float) and ann is not Any:
            # allow int specifically when integer constraint — shape-only so int|float ok
            if not (
                ann is int
                or ann is float
                or (origin is not None and set(get_args(ann)) <= {int, float})
            ):
                mismatches.append(f"{path}: expected number type, got {ann!r}")
        return
    if expected is str and ann is not str and ann is not Any:
        mismatches.append(f"{path}: expected str, got {ann!r}")
    if expected is bool and ann is not bool and ann is not Any:
        mismatches.append(f"{path}: expected bool, got {ann!r}")


def _strip_optional(ann: Any) -> tuple[Any, bool]:
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is None:
        return ann, False
    # Optional[T] / T | None
    if type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0], True
    return ann, False


def model_to_ordered_object(model: Any, *, schema_marker: str | None = None) -> JSONObject:
    """Serialize dataclass/BaseModel to ordered JSONObject using field declaration order."""
    from datorium_client._json.value import from_python, new_object, new_string

    if isinstance(model, BaseModel):
        data = model.model_dump(by_alias=True, mode="json")
        # Rebuild in model_fields order
        obj = new_object()
        if schema_marker is not None:
            obj.set("$", new_string(schema_marker))
        for name, finfo in type(model).model_fields.items():
            wire = _pydantic_wire_name(name, finfo)
            if wire in data:
                obj.set(wire, from_python(data[wire]))
        # extras?
        for k, v in data.items():
            if not obj.has(k):
                obj.set(k, from_python(v))
        return obj
    if is_dataclass(model) and not isinstance(model, type):
        obj = new_object()
        if schema_marker is not None:
            obj.set("$", new_string(schema_marker))
        for f in dataclasses.fields(model):
            wire = _dataclass_wire_name(f)
            obj.set(wire, from_python(getattr(model, f.name)))
        return obj
    raise TypeError(f"unsupported model {type(model)!r}")


def python_from_sot(model_type: type[Any], sot: JSONObject) -> Any:
    """Build a model from SOT content (excluding metadata keys)."""
    from datorium_client._json.value import to_python
    from datorium_client.crud import content_without_meta

    content = to_python(content_without_meta(sot))
    assert isinstance(content, dict)
    if issubclass(model_type, BaseModel):
        return model_type.model_validate(content)
    return TypeAdapter(model_type).validate_python(content)


def datorium_ref_formats() -> Any:
    from datorium_client._schema.formats import StringFormatRegistry
    from datorium_client.refs import RefKind, parse_ref

    reg = StringFormatRegistry()

    def direct(v: str) -> bool:
        try:
            ref, ok = parse_ref(v)
        except ValueError:
            return False
        return ok and ref is not None and ref.kind == RefKind.DIRECT

    def cached(v: str) -> bool:
        try:
            ref, ok = parse_ref(v)
        except ValueError:
            return False
        return ok and ref is not None and ref.kind == RefKind.CACHED

    reg.register("DatoriumDirectRef", direct)
    reg.register("DatoriumCachedRef", cached)
    return reg
