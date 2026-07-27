"""Application and transport errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datorium_client.envelope import Result

CODE_WRONG_MACHINE = "wrongMachine"
CODE_VERSION_MISMATCH = "versionMismatch"
CODE_DOCUMENT_NOT_FOUND = "documentNotFound"
CODE_DOCUMENT_EXISTS = "documentExists"
CODE_UNAUTHENTICATED = "unauthenticated"
CODE_INVALID_TOKEN = "invalidToken"
CODE_TOKEN_EXPIRED = "tokenExpired"
CODE_DOCUMENT_STALE = "documentStale"
CODE_READ_MEMBER_STALE = "readMemberStale"
CODE_SEARCH_NOT_FOUND = "searchNotFound"

CATALOG_COLLECTION_NOT_FOUND = "collectionNotFound"
CATALOG_SCHEMA_VERSION_MISMATCH = "schemaVersionMismatch"


@dataclass
class AppError(Exception):
    """Logical / business failure from an HTTP 200 envelope with ok:false."""

    code: str
    message: str = ""
    errors: list[Any] = field(default_factory=list)
    result: Any = None
    shard_slot: str = ""
    correct_server: str = ""
    base_url: str = ""
    config_version: int = 0
    collection: str = ""
    id: str = ""
    command: str = ""

    def __str__(self) -> str:
        if self.message:
            return f"datorium: {self.code}: {self.message}"
        return f"datorium: {self.code}"


@dataclass
class TransportError(Exception):
    """Non-2xx HTTP or unreadable transport failure (not a missing document)."""

    status_code: int = 0
    body: str = ""
    err: BaseException | None = None

    def __str__(self) -> str:
        if self.err is not None:
            return f"datorium transport: {self.err}"
        body = self.body if len(self.body) <= 200 else self.body[:200] + "..."
        return f"datorium transport: HTTP {self.status_code}: {body}"

    def __cause__(self) -> BaseException | None:  # type: ignore[override]
        return self.err


@dataclass
class CatalogError(Exception):
    collection: str
    code: str
    expected: int = -1
    actual: int = -1

    def __str__(self) -> str:
        return f"datorium catalog: {self.collection}: {self.code}"


def is_app_code(err: BaseException, code: str) -> bool:
    return isinstance(err, AppError) and err.code == code


def app_error_from_result(res: Result) -> AppError:
    code = res.first_error_code() or "unknown"
    message = res.errors[0].message if res.errors else ""
    if code == "unknown" and not message:
        message = "ok:false without error codes"
    return AppError(
        code=code,
        message=message,
        errors=list(res.errors),
        result=res,
        shard_slot=res.string_field("shardSlot"),
        correct_server=res.string_field("correctServer"),
        base_url=res.string_field("baseURL"),
        config_version=res.int_field("configVersion"),
        collection=res.string_field("collection"),
        id=res.string_field("id"),
        command=res.string_field("command"),
    )
