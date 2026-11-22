#!/usr/bin/env python3
"""Render the lock from the data under ``$HOME``, through the real seams.

The sibling of ``screenshot_states.py`` (split out for the 250-line cap; the
scripts may not import each other, see CLAUDE.md). That harness renders fixed
states over the cached pool; this one renders whatever the data dirs under
``$HOME`` say, the way ``cmd_lock`` would: the pool ranked by ``resolve_pool``
(unit-first, ``_unit_rank``), the unit screen from ``_unit_view.unit_view``,
the header from the real ledger's decision. It exists so the first screen kuhy
will see can be photographed from a copy of his own data before it ships
(build-desktop-ui L4/L5): five sessions once built a lock that looked unchanged
on day one.

**Point** ``HOME`` **at a scratch copy, never at the real one**, and run it on a
private Xvfb. Production mode (no demo fixture, no demo close button) with
``write_ledger`` off: nothing is seeded, minted, charged or settled, and the
lock's own theory poll does not run (it lives behind ``write_ledger``). The
network is stubbed: the recent-AC feed answers an empty list and every other
query (the pool refresh, the live solved check of the top rows) gets no
``question`` envelope, which the guard reads as "could not check".

``LEETCODE_GUARD_SHOT_KEY`` names a scratch HMAC key for a copy re-signed with
it; unset means the shared key, read only. Like ``screenshot_states.py`` this
writes no image: capture inside the ``QUIT_AFTER_MS`` window. From the repo root,
with ``HOME=<scratch>``, ``PYTHONUSERBASE=~/.local`` and ``DISPLAY=:N``::

    python3 -m scripts.screenshot_real
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, datetime
import os
from pathlib import Path
import pwd
import sys
import tempfile
from typing import TYPE_CHECKING

from leetcode_guard._auth import AuthState
from leetcode_guard._constants import LEDGER_FILE, POOL_CACHE_FILE
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps, GuardSeams
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard._unit_view import unit_view

if TYPE_CHECKING:
    from collections.abc import Callable

QUIT_AFTER_MS = 6000
"""Longer than the states harness: the pool cache is ~1 MB and read twice."""

KEY_ENV = "LEETCODE_GUARD_SHOT_KEY"
NOW = datetime.now(tz=UTC).astimezone()
SIGNED_OUT = AuthState(cookies=None, note="Not signed in (screenshot harness).")
EMPTY_FEED = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="0 recent")


class Inline:
    """Runs work on the calling thread so nothing is in flight while we shoot."""

    def submit(self, fn: Callable[[], object]) -> Future[object]:
        """Mirror ``SubmitsWork.submit`` without a thread."""
        future: Future[object] = Future()
        future.set_result(fn())
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


def stub_post(_query: str, _variables: dict[str, object]) -> GraphQLResult:
    """An empty recent feed; no ``question`` envelope, so "could not check"."""
    return GraphQLResult(data={"recentAcSubmissionList": []})


def build(workdir: Path) -> LeetcodeGuard:
    """The production lock over ``$HOME``'s data, today as that data says.

    No day pins, unlike ``screenshot_states``: free, sick and focus days are
    read from the same scratch ``HOME``, so the shot is the day the copy shows.
    """
    key = os.environ.get(KEY_ENV)
    key_file = Path(key) if key else None
    ledger = load_ledger(LEDGER_FILE, key_file=key_file)
    pool = resolve_pool(
        stub_post,
        POOL_CACHE_FILE,
        now=NOW.timestamp(),
        solved=SolvedKnowledge(
            auth=SIGNED_OUT, slugs=solved_slugs(ledger), key_file=key_file
        ),
    )
    return LeetcodeGuard(
        demo_mode=False,
        deps=GuardDeps(
            ledger_path=LEDGER_FILE,
            escape_path=workdir / "escape.json",
            post=stub_post,
            username="kuchy",
            auth=SIGNED_OUT,
            pool=pool,
            probe=EMPTY_FEED,
            key_file=key_file,
            write_ledger=False,
            seams=GuardSeams(
                phase=unit_view(LEDGER_FILE, key_file=key_file),
                now=lambda: NOW,
                executor=Inline(),
                wait_turn=False,
                incident_path=workdir / "incidents.json",
            ),
        ),
    )


def main() -> int:
    """Refuse the real data dir, render, and exit once Tk has drawn it."""
    if Path.home() == Path(pwd.getpwuid(os.getuid()).pw_dir):
        sys.stderr.write("error: HOME must be a scratch copy, not the real one\n")
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        root = build(Path(tmp)).root
        root.after(QUIT_AFTER_MS, root.quit)
        # Two idle passes realise and place the widgets before the capture.
        root.update_idletasks()
        root.update()
        root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
