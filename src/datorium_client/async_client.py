"""Asynchronous smart DatoriumDB client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx

from datorium_client._constants import (
    API_PREFIX,
    DEFAULT_CREATE_AMBIGUOUS_VERIFY_DELAY,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    DEFAULT_WRONG_MACHINE_MAX,
    MAX_RESPONSE_BODY_BYTES,
)
from datorium_client._json.value import JSONObject
from datorium_client.client import Config, _meta_string
from datorium_client.command import build_command, build_command_ordered, ensure_operation_id
from datorium_client.crud import (
    ReadOptions,
    ReadResult,
    SearchResult,
    WriteResult,
    read_result_from_envelope,
    search_result_from_envelope,
    write_result_from_envelope,
)
from datorium_client.envelope import Result, decode_result
from datorium_client.errors import (
    CODE_DOCUMENT_EXISTS,
    CODE_DOCUMENT_STALE,
    CODE_READ_MEMBER_STALE,
    CODE_VERSION_MISMATCH,
    CODE_WRONG_MACHINE,
    AppError,
    TransportError,
    app_error_from_result,
    is_app_code,
)
from datorium_client.establishment import (
    Establishment,
    EstablishmentCache,
    parse_establishment,
    validate_catalog,
)
from datorium_client.ids import new_document_id
from datorium_client.routing import (
    route_document_read_candidates,
    route_document_write,
    route_search,
    sot_for_document,
)
from datorium_client.stale import StaleReadPolicy


class AsyncTokenSource(Protocol):
    async def token(self) -> str: ...


class _AsyncStaticToken:
    def __init__(self, value: str) -> None:
        self.value = value

    async def token(self) -> str:
        return self.value


class _SyncTokenAdapter:
    def __init__(self, source: Any) -> None:
        self._source = source

    async def token(self) -> str:
        return str(self._source.token())


class AsyncClient:
    def __init__(self, cfg: Config, *, http_client: httpx.AsyncClient | None = None) -> None:
        if not cfg.establishment_url.strip():
            raise ValueError("datorium: establishment_url is required")
        self.cfg = cfg
        self.cfg.establishment_url = cfg.establishment_url.rstrip("/")
        if cfg.token_source is not None:
            self._tokens: Any = _SyncTokenAdapter(cfg.token_source)
        elif cfg.token:
            self._tokens = _AsyncStaticToken(cfg.token)
        else:
            raise ValueError("datorium: token or token_source is required")
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=cfg.timeout or DEFAULT_TIMEOUT_SECONDS
        )
        self._cache = EstablishmentCache()
        self._user_agent = cfg.user_agent or DEFAULT_USER_AGENT
        self._wm_retries = (
            cfg.wrong_machine_retries
            if cfg.wrong_machine_retries > 0
            else DEFAULT_WRONG_MACHINE_MAX
        )
        self._tr_retries = cfg.transport_retries
        delay = cfg.create_ambiguous_verify_delay
        self._create_verify_delay = (
            DEFAULT_CREATE_AMBIGUOUS_VERIFY_DELAY if delay == 0 else delay
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    def cached_establishment(self) -> Establishment | None:
        return self._cache.get()

    async def health(self) -> Result:
        return await self._get(self.cfg.establishment_url, f"{API_PREFIX}/health", auth=False)

    async def ready(self) -> Result:
        return await self._get(self.cfg.establishment_url, f"{API_PREFIX}/ready", auth=False)

    async def establish(self, *collections: tuple[str, int]) -> Establishment:
        res = await self._get(
            self.cfg.establishment_url, f"{API_PREFIX}/establish", auth=True
        )
        if not res.ok:
            raise app_error_from_result(res)
        est = parse_establishment(res)
        if collections:
            validate_catalog(est, list(collections))
        self._cache.set(est)
        return est

    async def schema(self, collection: str, version: int) -> Result:
        path = f"{API_PREFIX}/schema/{collection}/{version}"
        res = await self._get(self.cfg.establishment_url, path, auth=True)
        if not res.ok:
            raise app_error_from_result(res)
        return res

    async def command(self, base_url: str, line: str) -> Result:
        return await self._post_command(base_url, line)

    async def create(
        self, collection: str, doc_id: str, content: dict[str, Any]
    ) -> WriteResult:
        if not doc_id:
            doc_id = new_document_id()
        detail = ensure_operation_id(dict(content))
        line = build_command("create", collection, doc_id, detail)
        return await self._execute_create(collection, doc_id, line)

    async def create_ordered(
        self, collection: str, doc_id: str, detail: JSONObject
    ) -> WriteResult:
        from datorium_client.command import ensure_operation_id_object

        if not doc_id:
            raise ValueError("document id required")
        ensure_operation_id_object(detail)
        line = build_command_ordered("create", collection, doc_id, detail)
        return await self._execute_create(collection, doc_id, line)

    async def read(
        self,
        collection: str,
        doc_id: str,
        opts: ReadOptions | None = None,
    ) -> ReadResult:
        detail: dict[str, Any] = {}
        if opts:
            if opts.extra_fields:
                detail["extraFields"] = True
            if opts.cache_summaries:
                detail["cacheSummaries"] = True
        line = build_command("read", collection, doc_id, detail)
        last_err: Exception | None = None
        est = await self._ensure_established()
        for primary in route_document_read_candidates(est, doc_id):

            def resolve(
                e: Establishment, p: tuple[str, str] = primary
            ) -> list[tuple[str, str]]:
                rest = [c for c in route_document_read_candidates(e, doc_id) if c != p]
                return [p, *rest]

            try:
                res = await self._execute_routed(line, resolve)
            except AppError as exc:
                if exc.code in (CODE_READ_MEMBER_STALE, CODE_DOCUMENT_STALE):
                    last_err = exc
                    if self.cfg.stale_read_policy == StaleReadPolicy.SURFACE:
                        raise
                    continue
                raise
            return read_result_from_envelope(res)
        if self.cfg.stale_read_policy == StaleReadPolicy.PREFER_SOT and last_err is not None:
            res = await self._execute_routed(
                line, lambda e: [sot_for_document(e, doc_id)]
            )
            return read_result_from_envelope(res)
        if last_err is not None:
            raise last_err
        res = await self._execute_routed(
            line, lambda e: route_document_read_candidates(e, doc_id)
        )
        return read_result_from_envelope(res)

    async def patch(
        self, collection: str, doc_id: str, detail: dict[str, Any]
    ) -> WriteResult:
        detail = ensure_operation_id(dict(detail))
        line = build_command("patch", collection, doc_id, detail)
        res = await self._execute_routed(
            line, lambda e: [route_document_write(e, doc_id)]
        )
        return write_result_from_envelope(res, collection=collection, doc_id=doc_id)

    async def patch_ordered(
        self, collection: str, doc_id: str, detail: JSONObject
    ) -> WriteResult:
        from datorium_client.command import ensure_operation_id_object

        ensure_operation_id_object(detail)
        line = build_command_ordered("patch", collection, doc_id, detail)
        res = await self._execute_routed(
            line, lambda e: [route_document_write(e, doc_id)]
        )
        return write_result_from_envelope(res, collection=collection, doc_id=doc_id)

    async def patch_with_version_retry(
        self,
        collection: str,
        doc_id: str,
        build: Callable[[ReadResult], dict[str, Any] | Awaitable[dict[str, Any]]],
    ) -> WriteResult:
        current = await self.read(collection, doc_id)
        built = build(current)
        if asyncio.iscoroutine(built):
            built_detail = await built
        else:
            built_detail = built
        detail = ensure_operation_id(built_detail)
        try:
            return await self.patch(collection, doc_id, detail)
        except AppError as exc:
            if not is_app_code(exc, CODE_VERSION_MISMATCH):
                raise
            current = await self.read(collection, doc_id)
            built = build(current)
            if asyncio.iscoroutine(built):
                built_detail = await built
            else:
                built_detail = built
            detail = ensure_operation_id(built_detail)
            return await self.patch(collection, doc_id, detail)

    async def delete(
        self, collection: str, doc_id: str, detail: dict[str, Any]
    ) -> WriteResult:
        detail = ensure_operation_id(dict(detail))
        line = build_command("delete", collection, doc_id, detail)
        res = await self._execute_routed(
            line, lambda e: [route_document_write(e, doc_id)]
        )
        return write_result_from_envelope(res, collection=collection, doc_id=doc_id)

    async def search(
        self,
        collection: str,
        search_name: str,
        variables: dict[str, Any] | None = None,
        path_segments: list[str] | None = None,
    ) -> SearchResult:
        line = build_command("search", collection, search_name, variables or {})
        res = await self._execute_routed(
            line, lambda e: [route_search(e, path_segments)]
        )
        return search_result_from_envelope(res)

    async def _execute_create(
        self, collection: str, doc_id: str, line: str
    ) -> WriteResult:
        try:
            res = await self._execute_routed(
                line, lambda e: [route_document_write(e, doc_id)]
            )
            return write_result_from_envelope(res, collection=collection, doc_id=doc_id)
        except AppError as exc:
            if is_app_code(exc, CODE_DOCUMENT_EXISTS):
                read = await self.read(collection, doc_id)
                if read._sot is not None:
                    return WriteResult(
                        result=read.result,
                        collection=collection,
                        id=doc_id,
                        schema=_meta_string(read._sot, "$"),
                        version=_meta_string(read._sot, "#"),
                        operation_id="",
                    )
            raise
        except TransportError:
            if self._create_verify_delay < 0:
                raise
            await asyncio.sleep(self._create_verify_delay)
            read = await self.read(collection, doc_id)
            if read._sot is not None:
                return WriteResult(
                    result=read.result,
                    collection=collection,
                    id=doc_id,
                    schema=_meta_string(read._sot, "$"),
                    version=_meta_string(read._sot, "#"),
                    operation_id="",
                )
            raise

    async def _execute_routed(
        self,
        line: str,
        resolve_candidates: Callable[[Establishment], list[tuple[str, str]]],
    ) -> Result:
        """Post a command with smart routing.

        On wrongMachine: always re-fetch establishment from the establishment
        server, then recompute the next hop from that fresh document. Bounce
        fields such as correctServer, baseURL, and configVersion are ignored
        for routing (configVersion on a non-establishment server is diagnostic
        only and not authoritative).
        """
        tried: set[str] = set()
        last_err: AppError | None = None
        est = await self._ensure_established()
        for _attempt in range(self._wm_retries + 1):
            next_url = ""
            for server_name, base in resolve_candidates(est):
                url = self._rewrite(server_name, base)
                if url and url not in tried:
                    next_url = url
                    break
            if not next_url:
                break
            tried.add(next_url)
            res = await self._post_command(next_url, line)
            if res.ok:
                return res
            err = app_error_from_result(res)
            if err.code != CODE_WRONG_MACHINE:
                raise err
            last_err = err
            est = await self.establish()
        if last_err is not None:
            raise last_err
        raise AppError(code=CODE_WRONG_MACHINE, message="wrongMachine retries exhausted")

    async def _ensure_established(self) -> Establishment:
        est = self._cache.get()
        if est is None:
            est = await self.establish()
        return est

    def _rewrite(self, server_name: str, base_url: str) -> str:
        rewrite = self.cfg.base_url_rewrite
        if server_name and server_name in rewrite and rewrite[server_name]:
            return rewrite[server_name].rstrip("/")
        if base_url in rewrite and rewrite[base_url]:
            return rewrite[base_url].rstrip("/")
        return base_url.rstrip("/")

    async def _bearer(self) -> str:
        tok = str(await self._tokens.token()).strip()
        if tok.startswith("Bearer "):
            tok = tok[len("Bearer ") :]
        if not tok:
            raise ValueError("datorium: empty bearer token")
        return tok

    async def _get(self, base_url: str, path: str, *, auth: bool) -> Result:
        return await self._request(
            "GET", base_url, path, body=None, content_type="", auth=auth
        )

    async def _post_command(self, base_url: str, line: str) -> Result:
        return await self._request(
            "POST",
            base_url,
            f"{API_PREFIX}/command",
            body=line.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            auth=True,
        )

    async def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        body: bytes | None,
        content_type: str,
        auth: bool,
    ) -> Result:
        last_err: Exception | None = None
        attempts = self._tr_retries + 1
        for i in range(attempts):
            try:
                return await self._request_once(
                    method, base_url, path, body=body, content_type=content_type, auth=auth
                )
            except TransportError as exc:
                last_err = exc
                if i + 1 < attempts:
                    await asyncio.sleep((i + 1) * 0.1)
        assert last_err is not None
        raise last_err

    async def _request_once(
        self,
        method: str,
        base_url: str,
        path: str,
        *,
        body: bytes | None,
        content_type: str,
        auth: bool,
    ) -> Result:
        url = base_url.rstrip("/") + path
        headers = {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if auth:
            headers["Authorization"] = f"Bearer {await self._bearer()}"
        try:
            resp = await self._http.request(method, url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise TransportError(err=exc) from exc
        raw = resp.content
        if len(raw) > MAX_RESPONSE_BODY_BYTES:
            raise TransportError(
                status_code=resp.status_code,
                body="response body exceeds 8 MiB limit",
            )
        if resp.status_code < 200 or resp.status_code >= 300:
            raise TransportError(
                status_code=resp.status_code,
                body=raw.decode("utf-8", errors="replace"),
            )
        return decode_result(raw)
