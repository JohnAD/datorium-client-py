"""RFC 6902 patch parse, apply, and diff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from datorium_client._json.codec import dumps, loads
from datorium_client._json.number import values_equal_number
from datorium_client._json.value import (
    VOID,
    JSONArray,
    JSONBoolean,
    JSONNull,
    JSONNumber,
    JSONObject,
    JSONString,
    JSONValue,
    VoidType,
    clone_value,
    is_void,
    new_array,
    new_object,
    new_string,
)
from datorium_client._patch.pointer import format_pointer, parse_array_index, parse_pointer
from datorium_client._schema.apply import apply_schema
from datorium_client._schema.compile import CompiledSchema


class PatchError(ValueError):
    pass


@dataclass
class PatchOp:
    op: str
    path: str
    value: JSONValue | VoidType = field(default_factory=lambda: VOID)
    from_path: str | None = None

    def to_object(self) -> JSONObject:
        obj = new_object()
        obj.set("op", new_string(self.op))
        obj.set("path", new_string(self.path))
        if self.op in ("add", "replace", "test"):
            if is_void(self.value):
                raise PatchError(f"{self.op} requires value")
            obj.set("value", clone_value(self.value))
        if self.op in ("move", "copy"):
            if self.from_path is None:
                raise PatchError(f"{self.op} requires from")
            obj.set("from", new_string(self.from_path))
        return obj


@dataclass
class Patch:
    ops: list[PatchOp] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.ops)

    def to_json(self) -> str:
        return dumps(patch_to_json_value(self))


def patch_to_json_value(patch: Patch) -> JSONArray:
    return new_array([op.to_object() for op in patch.ops])


def parse_patch(source: str | bytes | JSONValue | list[Any]) -> Patch:
    if isinstance(source, list):
        from datorium_client._json.value import from_python

        doc = from_python(source)
    elif isinstance(source, (str, bytes)):
        text = source if isinstance(source, str) else source.decode("utf-8")
        doc = loads(text)
    else:
        doc = source
    if not isinstance(doc, JSONArray):
        raise PatchError("patch must be an array")
    ops: list[PatchOp] = []
    for item in doc.items:
        if is_void(item):
            raise PatchError("void patch element not allowed")
        if not isinstance(item, JSONObject):
            raise PatchError("patch op must be an object")
        ops.append(_parse_op(item))
    return Patch(ops)


def _parse_op(obj: JSONObject) -> PatchOp:
    allowed = {"op", "path", "from", "value"}
    seen: set[str] = set()
    for k, _ in obj.items_non_void():
        if k not in allowed:
            raise PatchError(f"unknown patch field {k!r}")
        if k in seen:
            raise PatchError(f"duplicate patch field {k!r}")
        seen.add(k)
    op_v = obj.get("op")
    path_v = obj.get("path")
    if is_void(op_v) or not isinstance(op_v, JSONString):
        raise PatchError("op required")
    if is_void(path_v) or not isinstance(path_v, JSONString):
        raise PatchError("path required")
    op = op_v.value
    if op not in {"add", "remove", "replace", "test", "move", "copy"}:
        raise PatchError(f"invalid op {op!r}")
    patch_op = PatchOp(op=op, path=path_v.value)
    if op in ("add", "replace", "test"):
        val = obj.get("value")
        if is_void(val):
            raise PatchError(f"{op} requires value")
        patch_op.value = clone_value(val)
    if op in ("move", "copy"):
        fr = obj.get("from")
        if is_void(fr) or not isinstance(fr, JSONString):
            raise PatchError(f"{op} requires from")
        patch_op.from_path = fr.value
    return patch_op


def values_equal(a: JSONValue | VoidType, b: JSONValue | VoidType) -> bool:
    if is_void(a) and is_void(b):
        return True
    if is_void(a) or is_void(b):
        return False
    assert not isinstance(a, VoidType) and not isinstance(b, VoidType)
    if type(a) is not type(b):
        return False
    if isinstance(a, JSONNull):
        return True
    if isinstance(a, JSONBoolean) and isinstance(b, JSONBoolean):
        return a.value == b.value
    if isinstance(a, JSONString) and isinstance(b, JSONString):
        return a.value == b.value
    if isinstance(a, JSONNumber) and isinstance(b, JSONNumber):
        return values_equal_number(a.text, b.text)
    if isinstance(a, JSONArray) and isinstance(b, JSONArray):
        if len(a.items) != len(b.items):
            return False
        return all(values_equal(x, y) for x, y in zip(a.items, b.items, strict=True))
    if isinstance(a, JSONObject) and isinstance(b, JSONObject):
        am = {k: v for k, v in a.items_non_void()}
        bm = {k: v for k, v in b.items_non_void()}
        if set(am) != set(bm):
            return False
        return all(values_equal(am[k], bm[k]) for k in am)
    return False


def apply_patch(
    document: JSONValue,
    patch: Patch,
    *,
    schema: CompiledSchema | None = None,
) -> JSONValue:
    working: JSONValue | VoidType = clone_value(document)
    for op in patch.ops:
        working = _apply_op(working, op)
    if is_void(working):
        raise PatchError("document became void")
    assert not isinstance(working, VoidType)
    if schema is not None:
        working = apply_schema(working, schema)
    return working


def _apply_op(doc: JSONValue | VoidType, op: PatchOp) -> JSONValue | VoidType:
    segments = parse_pointer(op.path)
    if op.op == "add":
        return _add(doc, segments, op.value)
    if op.op == "remove":
        return _remove(doc, segments)
    if op.op == "replace":
        if is_void(_get(doc, segments)):
            raise PatchError("replace target missing")
        return _add(doc, segments, op.value) if segments else clone_value(op.value)
    if op.op == "test":
        current = _get(doc, segments)
        if not values_equal(current, op.value):
            raise PatchError("test failed")
        return doc
    if op.op == "move":
        assert op.from_path is not None
        if op.from_path != op.path and (
            op.path == op.from_path or op.path.startswith(op.from_path + "/")
        ):
            # from is prefix of path
            if op.path.startswith(op.from_path + "/") or op.path == op.from_path:
                raise PatchError("move from is prefix of path")
        src_segments = parse_pointer(op.from_path)
        value = _get(doc, src_segments)
        if is_void(value):
            raise PatchError("move source missing")
        doc = _remove(doc, src_segments)
        return _add(doc, segments, value)
    if op.op == "copy":
        assert op.from_path is not None
        value = _get(doc, parse_pointer(op.from_path))
        if is_void(value):
            raise PatchError("copy source missing")
        return _add(doc, segments, clone_value(value))
    raise PatchError(f"unknown op {op.op}")


def _get(doc: JSONValue | VoidType, segments: list[str]) -> JSONValue | VoidType:
    cur: JSONValue | VoidType = doc
    for seg in segments:
        if is_void(cur):
            return VOID
        if isinstance(cur, JSONObject):
            cur = cur.get(seg)
        elif isinstance(cur, JSONArray):
            idx = parse_array_index(seg, allow_append=False)
            assert idx is not None
            if idx < 0 or idx >= len(cur.items):
                return VOID
            cur = cur.items[idx]
        else:
            return VOID
    return cur


def _add(
    doc: JSONValue | VoidType, segments: list[str], value: JSONValue | VoidType
) -> JSONValue | VoidType:
    if is_void(value):
        raise PatchError("cannot add void")
    if not segments:
        return clone_value(value)
    return _mutate(doc, segments, value, mode="add")


def _remove(doc: JSONValue | VoidType, segments: list[str]) -> JSONValue | VoidType:
    if not segments:
        return VOID
    return _mutate(doc, segments, VOID, mode="remove")


def _mutate(
    doc: JSONValue | VoidType,
    segments: list[str],
    value: JSONValue | VoidType,
    *,
    mode: str,
) -> JSONValue | VoidType:
    if is_void(doc) and segments:
        raise PatchError("path missing")
    assert not isinstance(doc, VoidType) or not segments

    if len(segments) == 1:
        seg = segments[0]
        if isinstance(doc, JSONObject):
            out = doc.clone()
            if mode == "remove":
                if not out.has(seg):
                    raise PatchError("remove target missing")
                out.remove(seg)
            else:
                out.set(seg, clone_value(value))
            return out
        if isinstance(doc, JSONArray):
            allow_append = mode == "add"
            idx = parse_array_index(seg, allow_append=allow_append)
            items = [clone_value(v) for v in doc.items if not is_void(v)]
            if mode == "remove":
                assert idx is not None
                if idx < 0 or idx >= len(items):
                    raise PatchError("remove target missing")
                del items[idx]
            else:
                if idx is None or idx == len(items):
                    items.append(clone_value(value))
                elif 0 <= idx < len(items):
                    items.insert(idx, clone_value(value))
                else:
                    raise PatchError("array index out of range")
            return new_array(items)
        raise PatchError("cannot descend into scalar")

    seg = segments[0]
    rest = segments[1:]
    if isinstance(doc, JSONObject):
        child = doc.get(seg)
        if is_void(child):
            raise PatchError("path missing")
        new_child = _mutate(child, rest, value, mode=mode)
        out = doc.clone()
        if is_void(new_child):
            out.remove(seg)
        else:
            out.set(seg, new_child)
        return out
    if isinstance(doc, JSONArray):
        idx = parse_array_index(seg, allow_append=False)
        assert idx is not None
        if idx < 0 or idx >= len(doc.items):
            raise PatchError("path missing")
        items = [clone_value(v) for v in doc.items]
        items[idx] = _mutate(items[idx], rest, value, mode=mode)
        return new_array([v for v in items if not is_void(v)])
    raise PatchError("cannot descend into scalar")


def diff(
    before: JSONValue,
    after: JSONValue,
    *,
    schema: CompiledSchema | None = None,
) -> Patch:
    left = apply_schema(before, schema) if schema else before
    right = apply_schema(after, schema) if schema else after
    # Strip schema effects already applied; compare structure
    ops: list[PatchOp] = []
    _diff_into(left, right, [], ops)
    return Patch(ops)


def _diff_into(
    before: JSONValue | VoidType,
    after: JSONValue | VoidType,
    path: list[str],
    ops: list[PatchOp],
) -> None:
    if values_equal(before, after):
        return
    if is_void(before):
        ops.append(PatchOp(op="add", path=format_pointer(path), value=clone_value(after)))
        return
    if is_void(after):
        ops.append(PatchOp(op="remove", path=format_pointer(path)))
        return
    assert not isinstance(before, VoidType) and not isinstance(after, VoidType)
    if type(before) is not type(after):
        ops.append(PatchOp(op="replace", path=format_pointer(path), value=clone_value(after)))
        return
    if isinstance(before, JSONObject) and isinstance(after, JSONObject):
        before_map = {k: v for k, v in before.items_non_void()}
        after_map = {k: v for k, v in after.items_non_void()}
        for k, v in after.items_non_void():
            _diff_into(before_map.get(k, VOID), v, path + [k], ops)
        for k in sorted(set(before_map) - set(after_map)):
            ops.append(PatchOp(op="remove", path=format_pointer(path + [k])))
        return
    if isinstance(before, JSONArray) and isinstance(after, JSONArray):
        shared = min(len(before.items), len(after.items))
        for i in range(shared):
            _diff_into(before.items[i], after.items[i], path + [str(i)], ops)
        for i in range(len(before.items) - 1, shared - 1, -1):
            ops.append(PatchOp(op="remove", path=format_pointer(path + [str(i)])))
        for i in range(shared, len(after.items)):
            ops.append(
                PatchOp(
                    op="add",
                    path=format_pointer(path + [str(i)]),
                    value=clone_value(after.items[i]),
                )
            )
        return
    ops.append(PatchOp(op="replace", path=format_pointer(path), value=clone_value(after)))
