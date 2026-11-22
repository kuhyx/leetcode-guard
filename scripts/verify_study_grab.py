#!/usr/bin/env python3
"""Prove that study mode really does release the X global grab.

**No unit test can answer this**: over a MagicMock Tk root a released grab and
a held one look the same, the state the 2026-08-05 lockout was in. So this asks
gatelock's public ``RecoveryLoop.holds_grab()`` around a real suspend/resume
cycle on a throwaway display, as a module so ``leetcode_guard`` resolves from
the checkout (add ``--rework`` for the ``?`` entry)::

    xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_study_grab

Every way into study mode is pressed for real: Open, then the THEORY card's
learn button (with ``--rework``: a SOLVE row's ``?``), with a fake ``tutor``
first on ``PATH`` and a scratch ``HOME``, so the real one never runs. The check
that matters most is "STAYS released": a grab that comes *back* a second later
is the original bug wearing the fix as a disguise.
"""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from datetime import UTC, date, datetime
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import TYPE_CHECKING, Final

import freedays
import sickdays

from leetcode_guard import _browser as browser
from leetcode_guard import _focus, _gate
from leetcode_guard import _lock_study as lock_study
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import POOL_CACHE_FILE
from leetcode_guard._gatelock_internals import surface_map
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps, GuardSeams
from leetcode_guard._phase_view import PhaseView
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import rank_pool
from leetcode_guard._submissions import ProbeStatus, SolveProbe

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

NOW: Final = datetime.now(tz=UTC).astimezone()
PROBLEM_URL: Final = "https://example.invalid/problems/two-sum/"
SUBJECT: Final = "leetcode-easy-algorithms-in-typescript"
ROUTE: Final = f"/learn/{SUBJECT}/prefix-sums"
THEORY: Final = PhaseView(  # so the learn button is on the surface to press
    unit="prefix-sums",
    phase="theory",
    cards_taught=0,
    cards_total=1,
    lessons_ready=True,
    minutes_per_credit=12,
    theory_minutes_today=1,
    solved=0,
    total=2,
    learn_target=(SUBJECT, "prefix-sums"),
)
SOLVE: Final = replace(  # --rework: the ``?`` shows on SOLVE rows only
    THEORY, phase="solve", learn_target=None, rework_target=(SUBJECT, "prefix-sums")
)
SETTLE_SECONDS: Final = 2.5
"""Real time pumped before "STAYS released": 2.5 ``recovery_tick_ms`` (1 s).
Counting ``update()`` calls measured nothing; twenty return in milliseconds."""


class _Inline:
    """Runs the poller's work on the calling thread."""

    def submit(self, fn: Callable[[], object]) -> Future[object]:
        """Mirror ``SubmitsWork.submit`` without a thread."""
        future: Future[object] = Future()
        future.set_result(fn())
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


def _build_production_guard(workdir: Path, view: PhaseView) -> LeetcodeGuard:
    """A real production lock: global grab, VT disabled, no ledger writes.

    Built here, not imported from ``screenshot_states``: ``scripts/`` is not a
    package, and such an import fails mypy in CI (CLAUDE.md).

    Today is pinned to an ordinary day: on a real free or sick day the first
    poll rightly unlocks and ends study mode (2026-10-16 failed so). The poller
    binds the real ``_check``, so ``post`` must answer a well-formed empty feed.
    """
    _gate.GATE_START_DATE = date(2000, 1, 1)
    freedays.is_free_day = _focus.stands_down = lambda *_a, **_k: False
    sickdays.is_sick_day = sickdays.stands_down = lambda *_a, **_k: False
    sickdays.kept_lockers = lambda *_a, **_k: frozenset()
    cached = read_cache(POOL_CACHE_FILE)
    problems = tuple(rank_pool(cached.problems)) if cached else ()
    signed_out = AuthState(cookies=None, note="Not signed in.")
    probe = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="none recent")

    return LeetcodeGuard(
        demo_mode=False,
        deps=GuardDeps(
            ledger_path=workdir / "ledger.json",
            escape_path=workdir / "escape.json",
            post=lambda _q, _v: GraphQLResult(data={"recentAcSubmissionList": []}),
            username="kuchy",
            auth=signed_out,
            pool=PoolResolution(
                problems=problems, source="cache", notes=(signed_out.note,)
            ),
            probe=probe,
            write_ledger=False,
            seams=GuardSeams(
                incident_path=workdir / "incidents.json",
                wait_turn=False,
                executor=_Inline(),
                now=lambda: NOW,
                phase=lambda: view,
            ),
        ),
    )


class _Recorder:
    """Stands in for the browser so nothing is really launched."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, args: Sequence[str], **_kwargs: object) -> object:
        self.urls.append(args[-1])
        return object()


def _pump(guard: LeetcodeGuard, ticks: int = 2, seconds: float = 0.0) -> None:
    """Let Tk process what it was asked to, ``ticks`` times and for ``seconds``."""
    deadline = time.monotonic() + seconds
    for _ in range(ticks):
        guard.root.update()
    while time.monotonic() < deadline:
        guard.root.update()
        time.sleep(0.05)


def _holds_grab(guard: LeetcodeGuard) -> bool:
    """Gatelock's own answer, rather than a reimplementation that could drift."""
    return bool(guard.lock.recovery.holds_grab())


def _check(results: list[bool], label: str, *, ok: bool) -> None:
    """Record one assertion and print it either way."""
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def _fake_tutor(workdir: Path) -> Path:
    """A ``tutor`` first on PATH and a scratch HOME: the real one never runs."""
    bin_dir = workdir / "bin"
    bin_dir.mkdir()
    args = workdir / "tutor-args"
    (bin_dir / "tutor").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{args}"\n')
    (bin_dir / "tutor").chmod(0o700)
    os.environ["HOME"] = str(workdir)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    return args


def _cycle(guard: LeetcodeGuard, results: list[bool], what: str) -> None:
    """After a press: grab down, STILL down past a recovery tick, then back."""
    _pump(guard)
    # The feature rests on this: while held, the window gets no keystrokes.
    _check(results, f"{what}: study mode released the grab", ok=not _holds_grab(guard))
    _pump(guard, seconds=SETTLE_SECONDS)
    _check(results, f"{what}: the grab STAYS released", ok=not _holds_grab(guard))
    guard.back_to_lock()
    _pump(guard)
    _check(results, f"{what}: the lock took the grab back", ok=_holds_grab(guard))
    _check(results, f"{what}: every surface is mapped", ok=_surfaces_mapped(guard))


def main() -> int:
    """Drive a suspend/resume cycle per entry (Open, learn or ``?``)."""
    rework = sys.argv[1:] == ["--rework"]
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    print("Verifying the study-mode grab handover under PRODUCTION config:")

    workdir = Path(tempfile.mkdtemp(prefix="lg-grab-check-"))
    tutor_args = _fake_tutor(workdir)
    guard = _build_production_guard(workdir, SOLVE if rework else THEORY)
    # "Launch" without starting anything real: this harness is about the grab.
    spawn = _Recorder()
    lock_study.find_opener = lambda: "/bin/true"
    lock_study.launch = lambda url: browser.launch(url, spawn=spawn)

    results: list[bool] = []
    try:
        _pump(guard)
        if guard.run_state.config.resolved_grab() != "global":
            print("  [FAIL] this is not a production lock; nothing to prove")
            return 1
        _check(results, "the lock holds the grab", ok=_holds_grab(guard))

        guard.open_problem(PROBLEM_URL)
        _cycle(guard, results, "Open")
        _check(results, "the browser got the problem", ok=spawn.urls == [PROBLEM_URL])

        views = guard.frames.views.values()  # press the real button
        if rework:
            next(v.problems.rework[0] for v in views if v.problems.rework).invoke()
        else:
            next(v.phase.learn for v in views if v.phase is not None).invoke()
        _cycle(guard, results, "?" if rework else "learn")
        asked = tutor_args.read_text().split() if tutor_args.exists() else []
        slug = guard.model.problems[0].slug if rework else ""
        route = f"/rework/{SUBJECT}/prefix-sums/{slug}" if rework else ROUTE
        _check(results, f"the tutor got {route}", ok=asked == ["--route", route])
    finally:
        guard.close()

    failed = results.count(False)
    print(f"\nFAILED: {failed} of {len(results)}" if failed else "\nOK: all passed")
    return 1 if failed else 0


def _surfaces_mapped(guard: LeetcodeGuard) -> bool:
    """Whether every surface came back visible and on its own output.

    Needs a real X server: gatelock's recovery sets override-redirect *after*
    mapping, so a revived surface can come back managed, on the wrong monitor.
    """
    surfaces = guard.lock.surfaces
    for info in surfaces.infos():
        surface = surface_map(surfaces).get(info.output_name)
        if surface is None or not surface.window.winfo_ismapped():
            return False
    return True


if __name__ == "__main__":
    sys.exit(main())
