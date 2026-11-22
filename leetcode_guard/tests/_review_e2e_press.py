"""The scenarios of ``scripts/verify_review_first`` that press a button.

The review row's Open and the THEORY card's learn button, with a tutor stub
that works, cannot be started, exits 1 or takes its time.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g
from leetcode_guard.tests._review_e2e import ROUTE
from leetcode_guard.tests._review_e2e_cases import (
    FALLBACK_SECONDS,
    PRESS_SETTLE_SECONDS,
    SETTLE_SECONDS,
    armed,
    demo,
    due_and_swap,
    is_review,
    is_solve,
    new_world,
    planted,
    put_due,
)

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard.tests._review_e2e import State, World
    from leetcode_guard.tests._review_e2e_cases import Claims


def press(world: World) -> tuple[dict[str, object] | None, float]:
    """Arm on the review row, then click its Open: (the armed state, click time)."""
    st = armed(world, is_review)
    if st is None or st["btn"] is None:
        return None, time.time()
    # Measured 2026-11-22: a click in the first ~second after the row maps is
    # lost (the surfaces are still being raised); 1 s later it always lands.
    time.sleep(PRESS_SETTLE_SECONDS)
    return st, world.click(st["btn"])


def spawn_fails(base: Path) -> Claims:
    """The launcher cannot even start: the SOLVE rows come back, grab held."""
    world = new_world(base, "spawnfail", scope_shebang="#!/nonexistent/interp")
    put_due(world, due=True, seq=1)
    world.start_lock()
    st, at = press(world)
    back = world.wait(is_solve, after=at, timeout=FALLBACK_SECONDS) if st else None
    warned = world.lines("the review could not be opened")
    return [
        ("spawn fails: the SOLVE rows come back", back is not None),
        (
            "spawn fails: the grab is held",
            bool(back and back["grab"]) and world.grab_held(),
        ),
        (
            "spawn fails: never in study mode",
            not any(s["study"] for s in world.states()),
        ),
        (f"spawn fails: one warning ({len(warned)})", len(warned) == 1),
    ]


def launch(base: Path) -> Claims:
    """A working launcher: the review route, study mode, grab released and kept so."""
    world = new_world(base, "launch")
    put_due(world, due=True, seq=1)
    world.start_lock()
    st, at = press(world)
    studying = (
        world.wait(lambda s: bool(s["study"]), after=at, timeout=5) if st else None
    )
    time.sleep(SETTLE_SECONDS)
    after = world.last() or {}
    argv = world.recorded("tutor.argv")
    return [
        (
            f"launch: the tutor got --route {ROUTE} ({argv})",
            argv == [f"--route {ROUTE}"],
        ),
        ("launch: through the scope shim", len(world.recorded("scope.log")) == 1),
        ("launch: study mode, grab released", bool(studying and not studying["grab"])),
        (
            "launch: grab STAYS released after a recovery tick",
            bool(after.get("study") and not after.get("grab", True))
            and not world.grab_held(),
        ),
        ("launch: no browser", world.recorded("browser.log") == []),
    ]


def _marker(world: World) -> bool:
    return (world.home / "run/leetcode-guard/study.json").exists()


def _relocked(world: World, what: str, at: float) -> tuple[State | None, Claims]:
    """After a press whose launcher exits 1: study ends, grab back, marker gone."""
    left = world.wait(
        lambda s: not s["study"] and s["grab"] and not s["strip"],
        after=at + 0.1,
        timeout=FALLBACK_SECONDS,
    )
    entered = any(s["study"] for s in world.states() if s["t"] >= at)
    return left, [
        (f"{what} exits 1: study mode was entered first", entered),
        (f"{what} exits 1: study ends, strip gone", left is not None),
        (
            f"{what} exits 1: the grab is held again",
            left is not None and world.grab_held(),
        ),
        (f"{what} exits 1: the restart marker is gone", not _marker(world)),
    ]


def review_exits_1(base: Path) -> Claims:
    """The review launcher starts, then exits 1: the SOLVE rows come back."""
    world = new_world(base, "reviewexit1", script="exit 1")
    put_due(world, due=True, seq=1)
    world.start_lock()
    st, at = press(world)
    if st is None:
        return [("review exits 1: armed on the review row", False)]
    _, claims = _relocked(world, "review", at)
    back = world.wait(is_solve, after=at, timeout=FALLBACK_SECONDS)
    warned = world.lines("the review could not be opened")
    return [
        *claims,
        ("review exits 1: the SOLVE rows come back", back is not None),
        (f"review exits 1: one warning ({len(warned)})", len(warned) == 1),
    ]


def learn_exits_1(base: Path) -> Claims:
    """The learn launcher starts, then exits 1: the failure shows on the lock."""
    world = new_world(base, "learnexit1", script="exit 1")
    world.start_lock(extra={"E2E_THEORY": "1"})
    st = armed(world, lambda s: s["learn"] is not None)
    if st is None:
        return [("learn exits 1: armed on the THEORY card", False)]
    time.sleep(PRESS_SETTLE_SECONDS)
    at = world.click(st["learn"][:4])
    _, claims = _relocked(world, "learn", at)
    shown = world.wait(
        lambda s: s["learn"] is not None and s["learn"][4] == g.NO_ENTRY,
        after=at,
        timeout=FALLBACK_SECONDS,
    )
    return [
        *claims,
        (f"learn exits 1: {g.NO_ENTRY} on the button", shown is not None),
        (
            f"learn exits 1: {g.BLIND} on the status line",
            shown is not None and str(shown["status"]).startswith(g.BLIND),
        ),
    ]


def slow_ok(base: Path) -> Claims:
    """A launcher that takes 3 s and then exits 0 is not relocked."""
    world = new_world(base, "slowok", script="sleep 3; exit 0")
    put_due(world, due=True, seq=1)
    world.start_lock()
    st, at = press(world)
    studying = (
        world.wait(lambda s: bool(s["study"]), after=at, timeout=5) if st else None
    )
    time.sleep(3 + SETTLE_SECONDS)  # past the exit, then past a recovery tick
    after = world.last() or {}
    return [
        ("slow ok: study mode", studying is not None),
        (
            "slow ok: still studying, grab released, after it exited 0",
            bool(after.get("study") and not after.get("grab", True))
            and not world.grab_held(),
        ),
    ]


SCENARIOS: Final = (
    due_and_swap,
    planted,
    spawn_fails,
    launch,
    demo,
    review_exits_1,
    learn_exits_1,
    slow_ok,
)
