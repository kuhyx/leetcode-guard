"""Publish the status snapshot to Firebase RTDB for the status app.

TODO-status-app.md decisions 1 and 2: ``leetcode-guard/status`` holds the
snapshot and ``leetcode-guard/heartbeat`` the time of the last push. Every
harvest run and every ledger change pushes; the ~32 KB snapshot is written
only when its content changed (``_snapshot_dedup``), the heartbeat always.
Read by nothing but the app. Firebase only, through the shared ``~/.config/crdt-sync/``
credential via crdt_sync -- no GitHub transport.

**Stored as one JSON text leaf** (crdt_sync's convention, written by
``_snapshot_rtdb`` with the echo switched off), not an RTDB object tree.
RTDB silently drops ``null`` values and empty lists from a tree, which would
erase exactly the "unknown" sections the schema promises to carry; a string
leaf arrives byte for byte. The app decodes it once.

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
from leetcode_guard._snapshot_auth import connect as sign_in
from leetcode_guard._snapshot_dedup import (
    VOLATILE_KEY,
    content_hash,
    read_pushed_hash,
    write_pushed_hash,
)
from leetcode_guard._snapshot_rtdb import silent_store_for
from leetcode_guard._status_full import gather_full

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from leetcode_guard._snapshot_rtdb import TextStore

_logger: Final = logging.getLogger(__name__)

SNAPSHOT_PATH: Final = "leetcode-guard/status"

HEARTBEAT_PATH: Final = "leetcode-guard/heartbeat"
"""A JSON string leaf: the ISO time of the last push, written every minute."""

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


def _firebase_client() -> TextStore:
    """A signed-in RTDB client; raises crdt_sync's errors on any failure."""
    client = sign_in(FIREBASE_APP, timeout_seconds=PUSH_TIMEOUT_SECONDS)
    return silent_store_for(client, timeout_seconds=PUSH_TIMEOUT_SECONDS)


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
    snapshot: dict[str, Any], *, connect: Callable[[], TextStore] | None = None
) -> PushResult:
    """Write the heartbeat, and the snapshot too if its content changed.

    The heartbeat follows a *successful* snapshot write and is skipped after
    a failed one: a fresh heartbeat over stale content would tell the app
    everything is current. Never raises crdt_sync errors.
    """
    digest = content_hash(snapshot)
    changed = digest != read_pushed_hash()
    text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    beat = str(snapshot[VOLATILE_KEY])
    try:
        client = (_firebase_client if connect is None else connect)()
        if changed:
            client.put_file_text(SNAPSHOT_PATH, text, message="leetcode-guard: status")
            write_pushed_hash(digest)
        client.put_file_text(HEARTBEAT_PATH, beat, message="leetcode-guard: beat")
    except (ConfigError, FirebaseAuthError, RemoteSyncError, OSError) as exc:
        _logger.warning("snapshot push failed: %s", exc)
        return PushResult(pushed=False, reason=f"snapshot push failed: {exc}", size=0)
    if not changed:
        return PushResult(
            pushed=True, reason=f"unchanged; heartbeat {beat}", size=len(beat)
        )
    return PushResult(
        pushed=True,
        reason=f"pushed {len(text)} bytes to {SNAPSHOT_PATH} + heartbeat",
        size=len(text) + len(beat),
    )


def push_quietly(
    *, now: datetime | None = None, connect: Callable[[], TextStore] | None = None
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
