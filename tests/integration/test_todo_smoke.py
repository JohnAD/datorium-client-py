"""Optional Docker integration smoke test.

Requires a running DatoriumDB stack and environment variables:

- DATORIUM_ESTABLISHMENT_URL
- DATORIUM_TOKEN

Skip by default when unset.
"""

from __future__ import annotations

import os

import pytest

from datorium_client import Client, Config

pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_todo_create_read_delete() -> None:
    url = os.environ.get("DATORIUM_ESTABLISHMENT_URL")
    token = os.environ.get("DATORIUM_TOKEN")
    if not url or not token:
        pytest.skip("DATORIUM_ESTABLISHMENT_URL and DATORIUM_TOKEN required")

    with Client(Config(establishment_url=url, token=token)) as client:
        client.establish()
        wr = client.create(
            "Todos",
            "",
            {"$": "Todos:0", "title": "integration", "status": "open"},
        )
        read = client.read("Todos", wr.id)
        assert read.sot.get("title") == "integration"
        client.delete(
            "Todos",
            wr.id,
            {"$": "Todos:0", "#": wr.version or read.sot["#"]},
        )
