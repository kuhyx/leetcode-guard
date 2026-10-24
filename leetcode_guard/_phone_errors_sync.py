"""The harvester's phone-error step: read ``app_errors``, notify once per error.

Runs every minute after the snapshot push (``_harvest_run``), signed in as
the pusher (same ``FIREBASE_APP`` credential cache, so no second session).
Each error the phone reported is announced with ``notify-send`` exactly once,
deduped on device + first-seen; a repeat only bumps its count in the mirror.

**Nothing here can affect the gate.** :func:`sync_quietly` turns every
failure into a warning and a journal line. The mirror is written *before*
notifying, and a failed write notifies nothing -- otherwise the same error
would pop up every minute.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

from crdt_sync import ConfigError, FirebaseAuthError, RemoteSyncError

from leetcode_guard._phone_errors import (
    parse_phone_errors,
    read_mirror,
    write_mirror,
)
from leetcode_guard._snapshot_auth import connect as sign_in
from leetcode_guard._snapshot_push import FIREBASE_APP, PUSH_TIMEOUT_SECONDS
from leetcode_guard._snapshot_rtdb import silent_store_for

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

APP_ERRORS_PATH: Final = "leetcode-guard/app_errors"
"""One JSON string leaf per install, written by the status app."""

NOTIFY_TIMEOUT_SECONDS: Final = 5.0

TITLE: Final = "LeetGuard app error on the phone"


def fetch_phone_errors() -> object:
    """``app_errors`` as decoded JSON; raises crdt_sync's errors on failure."""
    client = sign_in(FIREBASE_APP, timeout_seconds=PUSH_TIMEOUT_SECONDS)
    store = silent_store_for(client, timeout_seconds=PUSH_TIMEOUT_SECONDS)
    return store.get_json(APP_ERRORS_PATH)


def send_notification(title: str, body: str) -> bool:
    """Show a desktop notification via ``notify-send``; False (logged) on failure."""
    binary = shutil.which("notify-send")
    if binary is None:
        _logger.warning("notify-send not found; no desktop notification: %s", body)
        return False
    try:
        result = subprocess.run(
            [binary, "--app-name=leetcode-guard", title, body],
            capture_output=True,
            text=True,
            timeout=NOTIFY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _logger.warning("desktop notification failed (%s): %s", exc, body)
        return False
    if result.returncode != 0:
        _logger.warning(
            "notify-send exited %d (%s); no desktop notification: %s",
            result.returncode,
            result.stderr.strip() or "no stderr; is a DBus session reachable?",
            body,
        )
        return False
    return True


def sync_phone_errors(
    fetch: Callable[[], object],
    *,
    notify: Callable[[str, str], bool],
    path: Path | None = None,
) -> str:
    """Mirror the phone's errors, then announce the new ones. Returns a line."""
    errors = parse_phone_errors(fetch())
    notified = read_mirror(path)[1]
    new = [error for error in errors if error.key not in notified]
    # Only keys still on the phone: an error it dropped cannot come back
    # with the same first-seen, so remembering it forever buys nothing.
    if not write_mirror(errors, {error.key for error in errors}, path=path):
        return "mirror not written; not notifying"
    for error in new:
        notify(
            TITLE,
            f"{error.message} (x{error.count}, first {error.first_seen}, "
            f"device {error.device[:8]})",
        )
    return f"{len(errors)} kept, {len(new)} new"


def sync_quietly() -> str:
    """:func:`sync_phone_errors` against RTDB; every expected failure is a line.

    Anything else escapes to ``_harvest_run``'s fence, which logs it the
    same way: by type, never by message.
    """
    try:
        return sync_phone_errors(fetch_phone_errors, notify=send_notification)
    except (
        ConfigError,
        FirebaseAuthError,
        RemoteSyncError,
        OSError,
        ValueError,
    ) as exc:
        # The type only: a requests message carries the URL and its ?auth=.
        _logger.warning("phone errors unavailable: %s", type(exc).__name__)
        return f"unavailable ({type(exc).__name__})"
