#!/usr/bin/env python3
"""Render one lock state and hold it on screen long enough to be photographed.

Exists because the two worst UI bugs in this repo were both invisible to the
test suite: the demo close button drawn *behind* the surfaces, and the escape
form that could never be submitted. Neither could have been caught by an
assertion -- only by looking.

**This script writes no image.** It takes one argument, the state name, and
ignores any second argument; capturing is the caller's job, and it must happen
inside the ~2.5s window this script stays up (see ``QUIT_AFTER_MS``). An earlier
version of this docstring showed an output path that ``main`` never read, which
produced a rendered window and no PNG.

Run under Xvfb so nothing touches the real display::

    Xvfb :90 -screen 0 1600x1200x24 &
    DISPLAY=:90 python3 -m scripts.screenshot_states locked &
    DISPLAY=:90 import -window root /tmp/locked.png

One caveat that will waste a run otherwise: with ``overrideredirect=True`` the
root is a *backdrop* behind the surfaces, so a single ``import -window root``
fired too early captures a uniformly charcoal image that looks like a
successfully photographed lock. Sample repeatedly for the duration and keep the
largest file -- a blank frame is a few hundred bytes, a painted one is tens of
kilobytes.

States: ``locked``, ``unlocked``, ``escape``, ``outage``, ``production``.
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, date, datetime
from pathlib import Path
import sys
import tempfile
from typing import TYPE_CHECKING

from leetcode_guard import _gate
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import POOL_CACHE_FILE
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import rank_pool
from leetcode_guard._submissions import AcSubmission, ProbeStatus, SolveProbe
from leetcode_guard._view_update import apply_viewmodel

if TYPE_CHECKING:
    from collections.abc import Callable

# How long the rendered state stays up before the script quits. The external
# screenshot must land inside this window; long enough to catch by polling,
# short enough that a forgotten run does not sit on a display forever.
QUIT_AFTER_MS = 2500

NOW = datetime.now(tz=UTC).astimezone()
SIGNED_OUT = AuthState(
    cookies=None, note="Not signed in -- already-solved problems are NOT filtered out."
)


class Inline:
    """Runs work on the calling thread so nothing is in flight while we shoot."""

    def submit(self, fn: Callable[[], object]) -> Future[object]:
        """Mirror ``SubmitsWork.submit`` without a thread.

        Zero-arg on purpose: that is the only shape the poller ever uses, so
        inventing varargs here would be a wider contract than reality.
        """
        future: Future[object] = Future()
        future.set_result(fn())
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


def real_pool() -> PoolResolution:
    """The cached pool, so screenshots show genuine problems."""
    cached = read_cache(POOL_CACHE_FILE)
    problems = tuple(rank_pool(cached.problems)) if cached else ()
    return PoolResolution(problems=problems, source="cache", notes=(SIGNED_OUT.note,))


def probe(*ids: str) -> SolveProbe:
    """An OK probe carrying the given submission ids."""
    return SolveProbe(
        status=ProbeStatus.OK,
        submissions=tuple(
            AcSubmission(i, i, i, int(NOW.timestamp()), "python3") for i in ids
        ),
        reason=f"{len(ids)} recent accepted submissions",
    )


def build(state: str, workdir: Path) -> LeetcodeGuard:
    """Construct a guard already in the requested state.

    The start date is pushed into the past first: these shots are meant to show
    the gate as it will look *in force*, not the inert pre-start screen.
    """
    _gate.GATE_START_DATE = date(2000, 1, 1)

    ledger_path = workdir / "ledger.json"
    ledger = Ledger()
    if state == "unlocked":
        # Three credits banked, so today is covered and two remain.
        append(
            ledger,
            [
                credit_entry(
                    AcSubmission(f"s{i}", "t", "two-sum", 0, "python3"),
                    day=local_today(),
                    now=NOW,
                )
                for i in range(3)
            ],
        )
        save_ledger(ledger_path, ledger)

    guard = LeetcodeGuard(
        demo_mode=state != "production",
        deps=GuardDeps(
            ledger_path=ledger_path,
            escape_path=workdir / "escape.json",
            incident_path=workdir / "incidents.json",
            post=lambda _q, _v: None,
            username="kuchy",
            auth=SIGNED_OUT,
            pool=real_pool(),
            probe=probe(),
            write_ledger=False,
            wait_turn=False,
            executor=Inline(),
            now=lambda: NOW,
        ),
    )
    guard._check = probe

    if state == "unlocked":
        guard._on_poll_result(probe("fresh-solve"))
    elif state == "escape":
        guard._open_escape()
    elif state == "outage":
        guard._outage_note = (
            "This machine has no working internet connection -- none of 3 "
            "independent hosts responded.\nReconnect and the gate carries on as "
            "normal. If you cannot, the machine unlocks after 5 minute(s) -- but "
            "only once you have written down what happened to the network."
        )
        guard._model = guard._build_model(probe())
        apply_viewmodel(guard._views.values(), guard._model)

    return guard


def main(argv: list[str]) -> int:
    """Render one state and exit once Tk has drawn it."""
    state = argv[1] if len(argv) > 1 else "locked"
    with tempfile.TemporaryDirectory() as tmp:
        guard = build(state, Path(tmp))
        # Two idle passes: the first realises the widgets, the second lets the
        # placement settle before the external screenshot fires.
        guard.root.update_idletasks()
        guard.root.update()
        guard.root.after(QUIT_AFTER_MS, guard.root.quit)
        guard.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
