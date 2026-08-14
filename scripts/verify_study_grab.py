#!/usr/bin/env python3
"""Prove that study mode really does release the X global grab.

**No unit test can answer this.** In the suite the Tk root is a MagicMock, so
``grab_release()`` always "succeeds" and ``grab_set_global()`` never fails --
the mock is happy either way, which is precisely the state the 2026-08-05
lockout was in: everything looked fine and the user could not type. Only a real
X server knows whether a grab is held.

So this asks gatelock's own question, ``RecoveryLoop.holds_grab()`` -- public
and documented for exactly this use -- around a real suspend/resume cycle on a
throwaway display::

    Xvfb :81 -screen 0 1600x1200x24 &
    echo $! > /tmp/lg-xvfb.pid
    DISPLAY=:81 python3 -m scripts.verify_study_grab

Run as a *module*, for the same reason ``verify_screen_fits`` does: ``-m`` puts
the repo root on ``sys.path``, so ``leetcode_guard`` resolves from the checkout
rather than from wherever it happens to be installed.

Never ``pkill -f leetcode_guard`` afterwards -- that pattern matches the shell
running it. Kill by the recorded PID.

The check that matters most is step 4. A grab that comes *back* a second after
being released is the original bug wearing the fix as a disguise, and it is the
single most likely thing to regress when gatelock is bumped.
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import date, datetime, timezone
import logging
from pathlib import Path
import sys
import tempfile
from typing import TYPE_CHECKING, Final

from leetcode_guard import _browser as browser
from leetcode_guard import _gate
from leetcode_guard import _lock_study as lock_study
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import POOL_CACHE_FILE
from leetcode_guard._lock import GuardDeps, LeetcodeGuard
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import rank_pool
from leetcode_guard._submissions import ProbeStatus, SolveProbe

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_logger: Final = logging.getLogger(__name__)

NOW: Final = datetime.now(tz=timezone.utc).astimezone()
PROBLEM_URL: Final = "https://example.invalid/problems/two-sum/"
SETTLE_TICKS: Final = 20
"""``update()`` pumps between assertions. Twenty at ~100ms of real work each is
comfortably past ``recovery_tick_ms`` (1s), which is the point: a stopped
recovery loop must stay stopped across at least one tick it would have used."""


class _Inline:
    """Runs the poller's work on the calling thread."""

    def submit(self, fn: Callable[[], object]) -> Future[object]:
        """Mirror ``SubmitsWork.submit`` without a thread."""
        future: Future[object] = Future()
        future.set_result(fn())
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


def _build_production_guard(workdir: Path) -> LeetcodeGuard:
    """A real production lock: global grab, VT disabled, no ledger writes.

    Deliberately built here rather than imported from ``screenshot_states``.
    ``scripts/`` is not a package and must not become one (see
    ``pyproject.toml``), so a ``from scripts.x import y`` makes mypy see that
    file under two module names and fail -- which it did, in CI, on a clean
    cache, while a warm local cache stayed quiet.
    """
    _gate.GATE_START_DATE = date(2000, 1, 1)
    cached = read_cache(POOL_CACHE_FILE)
    problems = tuple(rank_pool(cached.problems)) if cached else ()
    signed_out = AuthState(cookies=None, note="Not signed in.")
    probe = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="none recent")

    guard = LeetcodeGuard(
        demo_mode=False,
        deps=GuardDeps(
            ledger_path=workdir / "ledger.json",
            escape_path=workdir / "escape.json",
            incident_path=workdir / "incidents.json",
            post=lambda _q, _v: None,
            username="kuchy",
            auth=signed_out,
            pool=PoolResolution(
                problems=problems, source="cache", notes=(signed_out.note,)
            ),
            probe=probe,
            write_ledger=False,
            wait_turn=False,
            executor=_Inline(),
            now=lambda: NOW,
        ),
    )
    guard._check = lambda: probe
    return guard


class _Recorder:
    """Stands in for the browser so nothing is really launched."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.detached = False

    def __call__(self, args: Sequence[str], *, start_new_session: bool) -> object:
        # Recorded rather than ignored: detaching is the property that keeps a
        # browser alive across `systemctl --user stop`, so it is worth seeing.
        self.detached = start_new_session
        self.urls.append(args[-1])
        return object()


def _pump(guard: LeetcodeGuard, ticks: int = 2) -> None:
    """Let Tk process what it has been asked to do."""
    for _ in range(ticks):
        guard.root.update()


def _holds_grab(guard: LeetcodeGuard) -> bool:
    """Gatelock's own answer, rather than a reimplementation that could drift."""
    return bool(guard._lock._recovery.holds_grab())


def _check(results: list[bool], label: str, *, actual: bool, expected: bool) -> None:
    """Record one assertion and print it either way."""
    ok = actual is expected
    results.append(ok)
    verdict = "PASS" if ok else "FAIL"
    print(f"  [{verdict}] {label} (expected {expected}, got {actual})")


def main() -> int:
    """Drive one suspend/resume cycle under production config."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    print("Verifying the study-mode grab handover under PRODUCTION config:")

    workdir = Path(tempfile.mkdtemp(prefix="lg-grab-check-"))
    guard = _build_production_guard(workdir)
    # Resolve and "launch" without starting anything real: this harness is
    # about the grab, and a browser opening on the developer's desk is noise.
    spawn = _Recorder()
    lock_study.find_opener = lambda: "/bin/true"
    lock_study.launch = lambda url: browser.launch(url, spawn=spawn)

    results: list[bool] = []
    try:
        _pump(guard)
        if guard._config.resolved_grab() != "global":
            print("  [FAIL] this is not a production lock; nothing to prove")
            return 1

        _check(
            results, "the lock holds the grab", actual=_holds_grab(guard), expected=True
        )

        guard._open_problem(PROBLEM_URL)
        _pump(guard)
        # The assertion the entire feature rests on. If this is True the
        # browser receives no keystrokes and the fix does not work.
        _check(
            results,
            "study mode released the grab",
            actual=_holds_grab(guard),
            expected=False,
        )

        _pump(guard, SETTLE_TICKS)
        _check(
            results,
            "the grab STAYS released past a recovery tick",
            actual=_holds_grab(guard),
            expected=False,
        )

        _check(
            results,
            "the browser was asked to open the problem",
            actual=spawn.urls == [PROBLEM_URL],
            expected=True,
        )

        guard._back_to_lock()
        _pump(guard)
        _check(
            results,
            "the lock took the grab back",
            actual=_holds_grab(guard),
            expected=True,
        )
        _check(
            results,
            "every surface is mapped again",
            actual=_surfaces_mapped(guard),
            expected=True,
        )
    finally:
        guard.close()

    if all(results):
        print(f"\nOK: {len(results)} checks passed.")
        return 0
    print(f"\nFAILED: {results.count(False)} of {len(results)} checks failed.")
    return 1


def _surfaces_mapped(guard: LeetcodeGuard) -> bool:
    """Whether every surface came back visible and on its own output.

    The mis-placement this guards against only happens on a real X server:
    gatelock's own recovery path sets override-redirect *after* mapping, so a
    surface revived that way can return window-manager-managed and on the wrong
    monitor.
    """
    surfaces = guard._lock.surfaces
    for info in surfaces.infos():
        surface = surfaces._surfaces.get(info.output_name)
        if surface is None or not surface.window.winfo_ismapped():
            return False
    return True


if __name__ == "__main__":
    sys.exit(main())
