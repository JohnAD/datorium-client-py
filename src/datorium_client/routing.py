"""Shard-aware base URL selection."""

from __future__ import annotations

import random

from datorium_client import searchpath, shard
from datorium_client.establishment import Establishment


def route_document_write(est: Establishment, document_id: str) -> tuple[str, str]:
    """Return (server_name, base_url) for a write."""
    if not document_id:
        return _establishment_route(est)
    slot = shard.slot(document_id)
    assignment = est.assignment_for_slot(slot)
    if assignment is None or not assignment.sot_member:
        return _establishment_route(est)
    return assignment.sot_member, est.server_base_url(assignment.sot_member)


def route_document_read(est: Establishment, document_id: str) -> tuple[str, str]:
    """Return (server_name, base_url) for a read.

    Picks a SHARD_READ_MEMBER uniformly at random. Never uses PROXY_READ_MEMBER.
    """
    candidates = route_document_read_candidates(est, document_id)
    return candidates[0]


def route_document_read_candidates(
    est: Establishment, document_id: str
) -> list[tuple[str, str]]:
    """Shuffled list of (server_name, base_url) for read / failover.

    The first entry is the randomly chosen primary SHARD_READ_MEMBER; the rest
    are the remaining read members in random order for failover policies.
    """
    if not document_id:
        return [_establishment_route(est)]
    slot = shard.slot(document_id)
    assignment = est.assignment_for_slot(slot)
    if assignment is None or not assignment.read_members:
        return [_establishment_route(est)]
    names = list(assignment.read_members)
    random.shuffle(names)
    return [(n, est.server_base_url(n)) for n in names]


def route_search(
    est: Establishment,
    path_segments: list[str] | None,
) -> tuple[str, str]:
    """Route a search command.

    When path segments are known, prefer a randomly chosen SHARD_READ_MEMBER for
    that search shard; fall back to SHARD_SOT_MEMBER if no read members exist.
    Without path segments, send to the establishment server and rely on
    wrongMachine bounce.
    """
    if path_segments:
        slot = searchpath.shard_slot(path_segments)
        assignment = est.assignment_for_slot(slot)
        if assignment is not None:
            if assignment.read_members:
                name = random.choice(assignment.read_members)
                return name, est.server_base_url(name)
            if assignment.sot_member:
                return assignment.sot_member, est.server_base_url(assignment.sot_member)
    return _establishment_route(est)


def sot_for_document(est: Establishment, document_id: str) -> tuple[str, str]:
    return route_document_write(est, document_id)


def _establishment_route(est: Establishment) -> tuple[str, str]:
    name = est.general.establishment_server
    return name, est.server_base_url(name)
