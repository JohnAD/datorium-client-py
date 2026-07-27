"""Contract tests against versioned DatoriumDB golden fixtures."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from datorium_client import Client, Config, TransportError, is_app_code
from datorium_client.envelope import decode_result
from datorium_client.errors import (
    CODE_DOCUMENT_NOT_FOUND,
    CODE_WRONG_MACHINE,
    app_error_from_result,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "testdata" / "contract" / "golden"


@pytest.mark.contract
def test_read_not_found_is_ok_false_not_http_404() -> None:
    body = (GOLDEN / "read_not_found.json").read_bytes()
    res = decode_result(body)
    assert res.ok is False
    assert res.first_error_code() == CODE_DOCUMENT_NOT_FOUND
    err = app_error_from_result(res)
    assert is_app_code(err, CODE_DOCUMENT_NOT_FOUND)


@pytest.mark.contract
def test_http_404_is_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = Client(
        Config(establishment_url="http://example.test", token="t", http_client=http)
    )
    with pytest.raises(TransportError) as ei:
        client.health()
    assert ei.value.status_code == 404


@pytest.mark.contract
def test_wrong_machine_fixture() -> None:
    body = (GOLDEN / "create_wrong_machine.json").read_bytes()
    res = decode_result(body)
    assert res.ok is False
    err = app_error_from_result(res)
    assert err.code == CODE_WRONG_MACHINE
    assert err.correct_server or err.base_url


@pytest.mark.contract
@pytest.mark.parametrize(
    "name",
    [
        "create_ok.json",
        "read_ok.json",
        "patch_ok.json",
        "delete_ok.json",
        "read_not_found.json",
        "create_document_exists.json",
        "patch_version_mismatch.json",
        "create_wrong_machine.json",
    ],
)
def test_golden_decodes(name: str) -> None:
    res = decode_result((GOLDEN / name).read_bytes())
    assert res.env is not None
    assert isinstance(res.ok, bool)
