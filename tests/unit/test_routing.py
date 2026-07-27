"""Routing unit tests."""

from __future__ import annotations

from datorium_client.establishment import (
    Establishment,
    GeneralConfig,
    ServerInfo,
    ShardAssignment,
)
from datorium_client.routing import route_document_read, route_document_read_candidates
from datorium_client.shard import parse_range


def _est_two_readers() -> Establishment:
    est = Establishment(
        general=GeneralConfig(establishment_server="serverA", version=1),
        servers={
            "serverA": ServerInfo(name="serverA", base_url="http://a.test"),
            "serverB": ServerInfo(name="serverB", base_url="http://b.test"),
        },
        shard_assignments=[
            ShardAssignment(
                range=parse_range("00-FF"),
                sot_member="serverA",
                read_members=["serverA", "serverB"],
            )
        ],
    )
    return est


def test_read_picks_only_read_members() -> None:
    est = _est_two_readers()
    seen: set[str] = set()
    for _ in range(40):
        name, url = route_document_read(est, "01ABCDEFGHJKLMNPQRSTVWXYZ0")
        assert name in {"serverA", "serverB"}
        assert url in {"http://a.test", "http://b.test"}
        seen.add(name)
    assert seen == {"serverA", "serverB"}


def test_read_candidates_are_shuffled_permutation() -> None:
    est = _est_two_readers()
    names = {c[0] for c in route_document_read_candidates(est, "01ABCDEFGHJKLMNPQRSTVWXYZ0")}
    assert names == {"serverA", "serverB"}
