"""Defer the gate while the phone's morning session is earning the carrot.

wake-alarm distils the phone's morning (weigh-in, shower, dress, desk) into
``MORNING_SESSION_FILE``, HMAC-signed, always dated today, with an
``exempt_until`` when the morning is live or was completed in time. This
module never re-derives that policy: the whole decision is *signature ok,
dated today, now < exempt_until*. Missing, stale, failed or tampered all
mean "no deferral" -- the gate runs as it always has.

A run deferral, not ledger state: nothing here is written, so ``decide``
stays pure and a deleted file cannot mint an unlocked day.

The one wrinkle is a PC booted mid-morning: the file is not today's until
wake-alarm's ``Persistent=true`` timer catches up, which needs the network.
The arming run waits for that, bounded; ``--check`` and ``--status`` never do.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import time
from typing import TYPE_CHECKING

from gatelock.log_integrity import verify_entry_hmac

from leetcode_guard._constants import MORNING_SESSION_FILE
from leetcode_guard._daycost import local_today

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

# Only inside this local window is a non-today file worth waiting for: the
# refresher runs 07:00-11:00, so outside it "not today's" is the truth.
MORNING_WINDOW: tuple[tuple[int, int], tuple[int, int]] = ((7, 0), (11, 0))
MORNING_RETRY_SECONDS: float = 30.0
MORNING_POLL_SECONDS: float = 5.0


def _read_verified() -> dict[str, object] | None:
    """The file's entry when it exists, parses and verifies; else None.

    Missing is debug (it is the normal state outside the morning); anything
    else is a warning, because it means the refresher or the key is broken.
    """
    if not MORNING_SESSION_FILE.exists():
        _logger.debug("No morning session file at %s", MORNING_SESSION_FILE)
        return None
    try:
        entry = json.loads(MORNING_SESSION_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Cannot read %s: %s", MORNING_SESSION_FILE, exc)
        return None
    if not isinstance(entry, dict) or not verify_entry_hmac(entry):
        _logger.warning("Morning session file is not a signed object")
        return None
    return entry


def _load_today(now: datetime) -> dict[str, object] | None:
    """Today's verified entry, or None."""
    entry = _read_verified()
    if entry is None or entry.get("date") != local_today(now=now).isoformat():
        return None
    return entry


def _reason_from(entry: dict[str, object], now: datetime) -> str | None:
    """Why the gate defers at ``now``, or None when the entry grants nothing."""
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        return None
    try:
        exempt_until = datetime.fromisoformat(until)
    except ValueError:
        _logger.warning("Morning session exempt_until unreadable: %r", until)
        return None
    if now >= exempt_until:
        return None
    return f"morning session {entry.get('outcome')}, no gate until {exempt_until:%H:%M}"


def _in_window(now: datetime) -> bool:
    (start_h, start_m), (end_h, end_m) = MORNING_WINDOW
    minutes = now.hour * 60 + now.minute
    return start_h * 60 + start_m <= minutes < end_h * 60 + end_m


def defer_for_morning_session(
    now: datetime,
    *,
    wait: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """The reason to skip this arming run, or None to gate as usual.

    With ``wait``, a file that is not today's during the morning window is
    retried for up to ``MORNING_RETRY_SECONDS`` so a freshly booted PC gives
    wake-alarm's catch-up run a chance to land before the gate arms.
    """
    now = now.astimezone()
    entry = _load_today(now)
    waited = 0.0
    while entry is None and wait and _in_window(now) and waited < MORNING_RETRY_SECONDS:
        sleep(MORNING_POLL_SECONDS)
        waited += MORNING_POLL_SECONDS
        now = datetime.now(tz=UTC).astimezone()
        entry = _load_today(now)
    if entry is None:
        if waited:
            _logger.warning(
                "No morning session for today after %.0fs; "
                "is wake-alarm-session.timer running?",
                waited,
            )
        return None
    return _reason_from(entry, now)
