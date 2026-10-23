"""Publish the status snapshot to Firebase RTDB for the status app.

TODO-status-app.md decisions 1 and 2: one node, ``leetcode-guard/status``,
written after every harvest run and on every ledger change, read by nothing
but the app. Firebase only, through the shared ``~/.config/crdt-sync/``
credential via crdt_sync -- no GitHub transport.

**Stored as one JSON text leaf** (crdt_sync's ``put_file_text``), not an RTDB
object tree. RTDB silently drops ``null`` values and empty lists from a tree,
which would erase exactly the "unknown" sections the schema promises to
carry; a string leaf arrives byte for byte. The app decodes it once.

**A push never affects the gate.** Every failure is a warning and a
:class:`PushResult`; :func:`push_quietly` additionally catches anything else,
because its caller is the harvest timer.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from crdt_sync import ConfigError, FirebaseAuthError, RemoteSyncError

from leetcode_guard._coach_log import read_coach
from leetcode_guard._constants import EXIT_OK, PROGRESS_CACHE_FILE
from leetcode_guard._daycost import local_now
from leetcode_guard._profile_cache import refresh_profile
from leetcode_guard._progress import read_progress_cache
from leetcode_guard._snapshot import build_snapshot
from leetcode_guard._snapshot_auth import connect
from leetcode_guard._status_full import gather_full

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from crdt_sync import RemoteStore

_logger: Final = logging.getLogger(__name__)

SNAPSHOT_PATH: Final = "leetcode-guard/status"

FIREBASE_APP: Final = "leetcode_guard_status"
"""Names the credential cache. Not ``_sync.py``'s ``leetcode_guard``: a
per-minute pusher and the lock's ledger sync refreshing one token file on
their own schedules is the corruption crdt_sync's per-app cache exists to
prevent."""

PUSH_TIMEOUT_SECONDS: Final = 10.0

EXIT_PUSH_FAILED: Final = 1


@dataclass(frozen=True)
class PushResult:
    """What one push did, in words the journal can carry."""

    pushed: bool
    reason: str
    size: int


def _firebase_client() -> RemoteStore:
    """A signed-in RTDB client; raises crdt_sync's errors on any failure."""
    return connect(FIREBASE_APP, timeout_seconds=PUSH_TIMEOUT_SECONDS)


def gather_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    """Read every source and assemble the snapshot. Writes no ledger.

    The profile refresh is the one network call, and it is rate-limited by
    its own mirror (:mod:`leetcode_guard._profile_cache`).
    """
    moment = local_now(now=now)
    full = gather_full(now=moment)
    profile = refresh_profile(now=moment.timestamp(), credit_count=full.gate.credits)
    return build_snapshot(
        full,
        # Re-read: the refresh above may just have rewritten the mirror that
        # gather_full read a moment earlier.
        progress=read_progress_cache(PROGRESS_CACHE_FILE),
        profile=profile,
        coach=read_coach(),
        now=moment,
    )


def push_snapshot(
    snapshot: dict[str, Any], *, connect: Callable[[], RemoteStore] | None = None
) -> PushResult:
    """Write ``snapshot`` to :data:`SNAPSHOT_PATH`. Never raises crdt_sync errors."""
    text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    try:
        client = (_firebase_client if connect is None else connect)()
        client.put_file_text(SNAPSHOT_PATH, text, message="leetcode-guard: status")
    except (ConfigError, FirebaseAuthError, RemoteSyncError, OSError) as exc:
        _logger.warning("snapshot push failed: %s", exc)
        return PushResult(pushed=False, reason=f"snapshot push failed: {exc}", size=0)
    return PushResult(
        pushed=True,
        reason=f"pushed {len(text)} bytes to {SNAPSHOT_PATH}",
        size=len(text),
    )


def push_quietly(
    *, now: datetime | None = None, connect: Callable[[], RemoteStore] | None = None
) -> PushResult:
    """Gather and push, letting nothing escape -- the harvest timer calls this."""
    try:
        return push_snapshot(gather_snapshot(now=now), connect=connect)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("snapshot push raised")
        return PushResult(pushed=False, reason="snapshot push raised", size=0)


def cmd_push_snapshot() -> int:
    """``--push-snapshot``: one push, its outcome printed."""
    result = push_quietly()
    print(result.reason)
    return EXIT_OK if result.pushed else EXIT_PUSH_FAILED
