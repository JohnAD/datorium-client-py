"""Offline validation of Todo Compose fixtures (no Docker required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datorium_client.shard import parse_range, validate_full_coverage

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "fixtures" / "server1" / ".config"


@pytest.mark.unit
def test_todo_fixtures_parse_and_shard_coverage() -> None:
    for name in (
        "__general.json",
        "__servers.json",
        "__shard-map.json",
        "__auth.json",
        "Users.schema.json",
        "Users.schema.0.json",
        "TodoLists.schema.json",
        "TodoLists.schema.0.json",
        "Todos.schema.json",
        "Todos.schema.0.json",
        "Todos.search.byStatus.json",
    ):
        path = CFG / name
        assert path.is_file(), path
        json.loads(path.read_text())

    shard_doc = json.loads((CFG / "__shard-map.json").read_text())
    default = shard_doc["shardMap"]["default"]
    ranges = [parse_range(raw) for raw in default]
    validate_full_coverage(ranges)
    assert "00-7F" in default
    assert "80-FF" in default

    assert (ROOT / "secrets" / "dev-signing-key.pem").is_file()
    assert (ROOT / "secrets" / "bootstrap-secret.txt").is_file()
    assert (ROOT / "docker-compose.yml").is_file()
