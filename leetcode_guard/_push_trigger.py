"""Ask for a status-snapshot push when the production ledger changes.

Called from :func:`~leetcode_guard._ledger_io.save_ledger`, i.e. from inside
the gate, so three properties are load-bearing:

* **It imports nothing but** ``_constants``. The snapshot is built from the
  status read paths, which import the ledger; importing it here would be a
  cycle, and would put the snapshot inside the gate's import graph
  (``test_push_trigger.py`` walks that graph).
* **It never waits.** The push runs in a separate process; a slow LeetCode or
  Firebase can never hold a lock window or a harvest.
* **It never raises.** A spawn failure is a warning. The one-minute harvester
  pushes regardless, so a lost request costs at most a minute of staleness.

The child is started through ``systemd-run --user`` when that exists: a plain
child shares the caller's cgroup, and a oneshot unit's cgroup is killed the
moment its main process exits -- which for "already unlocked" is milliseconds
after the write.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import LEDGER_FILE

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

_SYSTEMD_RUN_FLAGS: Final = ("--user", "--no-block", "--collect", "--quiet")


def push_command() -> list[str]:
    """The command that runs one ``--push-snapshot``, detached."""
    inner = [sys.executable, "-m", "leetcode_guard", "--push-snapshot"]
    runner = shutil.which("systemd-run")
    return inner if runner is None else [runner, *_SYSTEMD_RUN_FLAGS, *inner]


def real_spawn(command: list[str]) -> None:
    """Start ``command`` in its own session and do not wait for it."""
    subprocess.Popen(  # pylint: disable=consider-using-with
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


_spawn = real_spawn
"""Rebound by the test suite's autouse rail, so no test ever spawns."""


def request_push(path: Path) -> bool:
    """Request a push if ``path`` is the production ledger. Never raises.

    Demo and test ledgers never publish: the demo deletes its ledger every
    run, and the app must only ever show the real one.
    """
    if path != LEDGER_FILE:
        return False
    try:
        _spawn(push_command())
    except OSError as exc:
        _logger.warning("could not request a snapshot push: %s", exc)
        return False
    return True
