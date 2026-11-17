#!/usr/bin/env python3
"""The two roles ``e2e_evening`` spawns, under its scratch ``$HOME``.

``child``: the real ``--production --evening`` entry with the outside world
faked (LeetCode network, HMAC key, snapshot push, Firebase sync, nudge port).
``seed`` / ``pay``: write the scratch ledger -- an old seeded one, or today's
signed leetcode ``charge`` row. Run only by ``e2e_evening`` (it sets ``$HOME``
and ``$E2E_KEY`` first); never by hand, never against live state.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

from gatelock import log_integrity

from leetcode_guard import _cli, _lock, _push_trigger
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._daycost import local_today
from leetcode_guard._harvest import SeedStamp, seed_ledger
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._settings import Client
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._net_fixtures import (
    pool_result,
    problem_row,
    recent_ac_result,
)

KEY = Path(os.environ["E2E_KEY"])
SLUGS = ("two-sum", "add-two-numbers", "3sum", "lru-cache")


def child() -> int:
    """Run ``--production --evening`` with every outside dependency faked."""
    log_integrity.DEFAULT_HMAC_KEY_FILE = KEY
    pool = pool_result([problem_row(slug) for slug in SLUGS], total=len(SLUGS))

    def post(query: str, _variables: object) -> object:
        return recent_ac_result([]) if "recentAcSubmissions" in query else pool

    _push_trigger._spawn = lambda _command: None  # pylint: disable=protected-access
    _lock.sync_quietly = lambda *_a, **_k: None
    _cli.NUDGE_PORT = None
    _cli.build_client = lambda: Client(
        post=post, auth=AuthState(cookies=None, note="e2e"), username="e2e"
    )
    return _cli.main(["--production", "--evening"])


def ledger(action: str) -> int:
    """``seed``: an old ledger, unpaid today. ``pay``: add today's charge."""
    log_integrity.DEFAULT_HMAC_KEY_FILE = KEY
    _push_trigger._spawn = lambda _command: None  # pylint: disable=protected-access
    now = datetime.now().astimezone()
    if action == "seed":
        probe = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="e2e")
        old = local_today(now=now) - timedelta(days=3)
        stamp = SeedStamp(day=old, now=now, key_file=KEY)
        seed_ledger(Ledger(), probe, stamp=stamp, path=LEDGER_FILE)
        return 0
    rows = load_ledger(LEDGER_FILE, key_file=KEY)
    append(rows, [charge_entry(local_today(now=now), now=now, key_file=KEY)])
    return 0 if save_ledger(LEDGER_FILE, rows) else 1


if __name__ == "__main__":
    sys.exit(child() if sys.argv[1] == "child" else ledger(sys.argv[1]))
