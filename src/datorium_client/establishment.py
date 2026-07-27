"""Establishment document parsing and cache."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from datorium_client._json.value import JSONNumber, JSONObject, JSONString, JSONValue, is_void
from datorium_client.envelope import Result
from datorium_client.errors import (
    CATALOG_COLLECTION_NOT_FOUND,
    CATALOG_SCHEMA_VERSION_MISMATCH,
    CatalogError,
)
from datorium_client.shard import Range, parse_range, validate_full_coverage


@dataclass
class GeneralConfig:
    name: str = ""
    establishment_server: str = ""
    version: int = 0
    read_member_checkin_seconds: int = 0
    cache_update_checkin_seconds: int = 0
    read_member_failed_checkins_before_stale: int = 0


@dataclass
class ServerInfo:
    name: str
    base_url: str


@dataclass
class ShardAssignment:
    range: Range
    sot_member: str = ""
    read_members: list[str] = field(default_factory=list)
    proxy_read_members: list[str] = field(default_factory=list)


@dataclass
class SchemaEntry:
    version: int
    schema: JSONValue


@dataclass
class Establishment:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    servers: dict[str, ServerInfo] = field(default_factory=dict)
    shard_assignments: list[ShardAssignment] = field(default_factory=list)
    schemas: dict[str, SchemaEntry] = field(default_factory=dict)
    searches: JSONValue | None = None
    auth: JSONValue | None = None
    env: JSONObject | None = None

    def assignment_for_slot(self, slot: int) -> ShardAssignment | None:
        for a in self.shard_assignments:
            if a.range.contains(slot):
                return a
        return None

    def server_base_url(self, name: str) -> str:
        info = self.servers.get(name)
        if info is None:
            return ""
        return info.base_url.rstrip("/")


class EstablishmentCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._value: Establishment | None = None

    def get(self) -> Establishment | None:
        with self._lock:
            return self._value

    def set(self, value: Establishment) -> None:
        with self._lock:
            self._value = value


def parse_establishment(res: Result) -> Establishment:
    if res.env is None:
        raise ValueError("empty establishment envelope")
    env = res.env
    est = Establishment(env=env)
    general = env.get("general")
    if isinstance(general, JSONObject):
        est.general = GeneralConfig(
            name=_str(general, "name"),
            establishment_server=_str(general, "establishmentServer"),
            version=_int(general, "version"),
            read_member_checkin_seconds=_int(general, "readMemberCheckinSeconds"),
            cache_update_checkin_seconds=_int(general, "cacheUpdateCheckinSeconds"),
            read_member_failed_checkins_before_stale=_int(
                general, "readMemberFailedCheckinsBeforeStale"
            ),
        )
    servers = env.get("servers")
    if isinstance(servers, JSONObject):
        for name, info in servers.items_non_void():
            if isinstance(info, JSONObject):
                est.servers[name] = ServerInfo(name=name, base_url=_str(info, "baseURL"))
    shard_map = env.get("shardMap")
    if isinstance(shard_map, JSONObject):
        default = shard_map.get("default")
        if isinstance(default, JSONObject):
            ranges: list[Range] = []
            for raw_range, members in default.items_non_void():
                r = parse_range(raw_range)
                ranges.append(r)
                assignment = ShardAssignment(range=r)
                if isinstance(members, JSONObject):
                    assignment.sot_member = _str(members, "SHARD_SOT_MEMBER")
                    read = members.get("SHARD_READ_MEMBER")
                    if isinstance(read, type(None)):
                        pass
                    from datorium_client._json.value import JSONArray

                    if isinstance(read, JSONArray):
                        assignment.read_members = [
                            v.value for v in read.items if isinstance(v, JSONString)
                        ]
                    proxy = members.get("PROXY_READ_MEMBER")
                    if isinstance(proxy, JSONArray):
                        assignment.proxy_read_members = [
                            v.value for v in proxy.items if isinstance(v, JSONString)
                        ]
                est.shard_assignments.append(assignment)
            validate_full_coverage(ranges)
    schemas = env.get("schemas")
    if isinstance(schemas, JSONObject):
        for coll, entry in schemas.items_non_void():
            if isinstance(entry, JSONObject):
                ver = _int(entry, "version")
                schema_doc = entry.get("schema")
                if not is_void(schema_doc):
                    est.schemas[coll] = SchemaEntry(version=ver, schema=schema_doc)  # type: ignore[arg-type]
    searches = env.get("searches")
    if not is_void(searches):
        est.searches = searches  # type: ignore[assignment]
    auth = env.get("auth")
    if not is_void(auth):
        est.auth = auth  # type: ignore[assignment]
    return est


def validate_catalog(
    est: Establishment, refs: list[tuple[str, int]]
) -> None:
    """refs is list of (collection_name, schema_version)."""
    mismatches: list[CatalogError] = []
    for name, version in refs:
        entry = est.schemas.get(name)
        if entry is None:
            mismatches.append(
                CatalogError(collection=name, code=CATALOG_COLLECTION_NOT_FOUND)
            )
            continue
        if entry.version != version:
            mismatches.append(
                CatalogError(
                    collection=name,
                    code=CATALOG_SCHEMA_VERSION_MISMATCH,
                    expected=version,
                    actual=entry.version,
                )
            )
    if mismatches:
        # Raise first; attach all via ExceptionGroup on 3.11+
        if len(mismatches) == 1:
            raise mismatches[0]
        raise ExceptionGroup("catalog validation failed", mismatches)


def _str(obj: JSONObject, key: str) -> str:
    v = obj.get(key)
    if isinstance(v, JSONString):
        return v.value
    return ""


def _int(obj: JSONObject, key: str) -> int:
    v = obj.get(key)
    if isinstance(v, JSONNumber):
        try:
            return int(v.text.split(".")[0].split("e")[0].split("E")[0])
        except ValueError:
            return 0
    return 0
