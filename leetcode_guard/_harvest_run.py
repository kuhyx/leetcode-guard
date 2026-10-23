"""Credit solves made while no lock window is up: the one-minute harvest.

Run as ``python3 -m leetcode_guard._harvest_run`` by
``leetcode-guard-harvest.timer``. Until 2026-10-17 credits were minted only by
the lock's poll loop, so a solve made on a sick day, a settled day, or after the
13:00 slot never reached the ledger -- five accepted submissions that day showed
"Today: 0" and earned neither consumer's hour. This does the same harvest
without a window.

It is a separate entry point rather than a ``_cli`` flag on purpose: every
``_cli`` flag is documented as unable to move the balance, and this one does.
Credits still come only from LeetCode's own recent-AC feed, so the "credits must
verify" rule holds unchanged.

Four rules, each pinned in ``test_harvest_run.py``:

* **Never hold the instance lock.** ``cmd_lock`` stands down when it is taken,
  and systemd stamps the slot as run anyway, so a harvest overlapping the 09:00
  fire would skip that day's gate. The lock is only *peeked* and released.
* **Never write while a lock is up.** The lock keeps its whole ledger in memory
  and saves it whole, which would erase a second writer's entries. Its own poll
  loop harvests, so standing aside loses nothing.
* **Never seed.** Seeding is the lock's first run and deliberately does not arm.
* **Settle only in a run that minted a credit.** A bare tick spending banked
  credit at 00:05 would pay for a day that may yet be marked free or sick.
"""

from __future__ import annotations

from datetime import date, datetime
import fcntl
import logging
import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import (
    EXIT_OK,
    GATE_START_DATE,
    HARVEST_LOCK_FILE,
    INSTANCE_LOCK_FILE,
    LEDGER_FILE,
)
from leetcode_guard._daycost import local_today
from leetcode_guard._gate import apply_decision
from leetcode_guard._gate_today import decide_today
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding
from leetcode_guard._instance import acquire
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._settings import build_client
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

LOCK_IS_UP: Final = "a lock is up; its own poll loop harvests"


def lock_is_up(path: Path) -> bool:
    """Whether a lock run holds the instance lock, without keeping it.

    An unopenable lock file counts as held: unable to tell means the lock may
    own the ledger, and a write then could be erased.
    """
    try:
        handle = path.open("a+", encoding="utf-8")
    except OSError as exc:
        _logger.warning("cannot open %s, assuming a lock is up: %s", path, exc)
        return True
    with handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _logger.warning("a lock run holds %s", path)
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def _harvest_once(day: date, now: datetime, key_file: Path | None) -> str:
    """The harvest proper; the caller holds the harvest lock."""
    if lock_is_up(INSTANCE_LOCK_FILE):
        return LOCK_IS_UP
    client = build_client()
    probe = fetch_recent_ac(client.post, client.username)
    if probe.status is not ProbeStatus.OK:
        return f"could not check: {probe.reason}"
    # Re-peek after the network round trip: a lock armed meanwhile has
    # already loaded the ledger, and it will save over whatever we write.
    if lock_is_up(INSTANCE_LOCK_FILE):
        return LOCK_IS_UP
    ledger = load_ledger(LEDGER_FILE)
    if needs_seeding(ledger):
        return "ledger not seeded yet; the lock's first run seeds it"
    result = harvest(ledger, probe, day=day, now=now, key_file=key_file)
    if not result.gained:
        return f"nothing new ({result.already_known} known)"
    commit_harvest(ledger, result, LEDGER_FILE)
    decision = decide_today(ledger, day=day, now=now, key_file=key_file)
    settled = not decision.locked and apply_decision(ledger, decision, LEDGER_FILE)
    return f"credited {result.gained}" + ("; settled today" if settled else "")


def run_harvest(*, key_file: Path | None = None) -> str:
    """One harvest, under the harvest lock. Returns the line to print."""
    now = datetime.now().astimezone()
    day = local_today(now=now)
    if day < GATE_START_DATE:
        return f"gate not active until {GATE_START_DATE}; nothing to do"
    held = acquire(HARVEST_LOCK_FILE)
    if held is None:
        return "another harvest is running"
    try:
        return _harvest_once(day, now, key_file)
    finally:
        held.release()


def main(*, key_file: Path | None = None) -> int:
    """Entry point for the timer unit."""
    configure_logging()
    print(run_harvest(key_file=key_file))
    # Every run, after the harvest lock is released and whatever it found:
    # the heartbeat is the status app's freshness signal. In-process on
    # purpose -- a detached child would die with this oneshot's cgroup.
    print(f"snapshot: {_push_line()}")
    return EXIT_OK


def _push_line() -> str:
    """Push the status snapshot; nothing it does can stop a harvest.

    Imported here, not at the top: the harvest mints credits, the snapshot is
    display-only, and a snapshot-only breakage -- a crdt_sync bump dropping a
    name only the push uses, a bug in a snapshot module -- must cost the push,
    never the process start (``test_harvest_isolation.py``).
    """
    try:
        from leetcode_guard._snapshot_push import (  # pylint: disable=import-outside-toplevel
            push_quietly,
        )

        return push_quietly().reason
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("snapshot push unavailable: %s", exc, exc_info=True)
        return f"push unavailable: {exc}"


if __name__ == "__main__":
    sys.exit(main())
