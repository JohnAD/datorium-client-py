"""Pure Python smart client for DatoriumDB."""

from datorium_client.async_client import AsyncClient
from datorium_client.client import Client, Config, StaticToken, TokenSource
from datorium_client.collection import Collection, CollectionItem, CollectionPatch, DocMeta
from datorium_client.crud import ReadOptions, ReadResult, SearchResult, WriteResult
from datorium_client.errors import (
    CODE_DOCUMENT_EXISTS,
    CODE_DOCUMENT_NOT_FOUND,
    CODE_DOCUMENT_STALE,
    CODE_INVALID_TOKEN,
    CODE_READ_MEMBER_STALE,
    CODE_SEARCH_NOT_FOUND,
    CODE_TOKEN_EXPIRED,
    CODE_UNAUTHENTICATED,
    CODE_VERSION_MISMATCH,
    CODE_WRONG_MACHINE,
    AppError,
    CatalogError,
    TransportError,
    is_app_code,
)
from datorium_client.ordered import Null, Void
from datorium_client.refs import Ref, RefKind, format_cached, format_direct, parse_ref
from datorium_client.stale import StaleReadPolicy

__all__ = [
    "AsyncClient",
    "Client",
    "Config",
    "StaticToken",
    "TokenSource",
    "Collection",
    "CollectionItem",
    "CollectionPatch",
    "DocMeta",
    "ReadOptions",
    "ReadResult",
    "SearchResult",
    "WriteResult",
    "AppError",
    "CatalogError",
    "TransportError",
    "is_app_code",
    "CODE_WRONG_MACHINE",
    "CODE_VERSION_MISMATCH",
    "CODE_DOCUMENT_NOT_FOUND",
    "CODE_DOCUMENT_EXISTS",
    "CODE_UNAUTHENTICATED",
    "CODE_INVALID_TOKEN",
    "CODE_TOKEN_EXPIRED",
    "CODE_DOCUMENT_STALE",
    "CODE_READ_MEMBER_STALE",
    "CODE_SEARCH_NOT_FOUND",
    "Ref",
    "RefKind",
    "parse_ref",
    "format_direct",
    "format_cached",
    "StaleReadPolicy",
    "Null",
    "Void",
]

__version__ = "0.1.0"
