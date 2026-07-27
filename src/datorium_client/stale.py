"""Configurable stale-read handling policy."""

from __future__ import annotations

from enum import StrEnum


class StaleReadPolicy(StrEnum):
    """What to do when a read member returns readMemberStale / documentStale.

    Default on Config is FAILOVER.
    """

    SURFACE = "surface"
    """Raise the first stale application error immediately."""

    FAILOVER = "failover"
    """Try other eligible SHARD_READ_MEMBER servers, then raise the last error."""

    PREFER_SOT = "prefer_sot"
    """After read-member stale failures, attempt the SHARD_SOT_MEMBER once."""
