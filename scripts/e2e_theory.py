#!/usr/bin/env python3
"""End-to-end checks of the theory-first lock on seeded scratch state.

Real entry points (``--production`` lock, the harvester, ``--status``) under a
scratch ``$HOME`` and key, a private Xvfb, LeetCode faked (``e2e_theory_roles``).
One case per call; the exit code is the verdict, and one line per case is
appended to ``~/data/claude-scratch/lc-stage4/e2e/results.txt``::

    python3 -m scripts.e2e_theory a|b|c|d|e|f

Cases (SPEC "The flow", "Guard rules for the new credit"): a THEORY arms with
the theory card; b teaching minutes pay the day, other modules pay nothing;
c SOLVE mints nothing after the flip and still pays solves; d cannot check;
e a finished unit moves on; f deleting files cannot mint.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import sys
from typing import TYPE_CHECKING

from leetcode_guard.tests._e2e_theory_cases import (
    case_d,
    case_e,
    case_f,
    check,
    needed,
    seeded,
)
from leetcode_guard.tests._e2e_world import ALGO, OUT, World
from leetcode_guard.tests._e2e_world import PAINTED_BYTES as PAINTED

if TYPE_CHECKING:
    from collections.abc import Callable

PS = [[ALGO, "prefix-sums"]]


def case_a(world: World) -> str:
    """THEORY, nothing paid: the lock arms leading with the theory card; C3 written."""
    seeded(world)
    world.role("flip", "prefix-sums/0/60")
    code, log, most = world.lock(
        seconds=20,
        until="home/.local/share/leetcode_guard/theory_phase.json",
        shot="theory",
    )
    model = world.model() or {}
    screen, view = model.get("screen") or {}, model.get("view") or {}
    check(
        code is None and most > 0,
        f"lock did not stay armed: {code} {most}\n{log[-800:]}",
    )
    check(
        screen.get("phase") == "theory" and screen.get("card"),
        f"no theory card: {screen}",
    )
    check(view.get("learn_target") == [ALGO, "prefix-sums"], f"learn target: {view}")
    row = world.phase_file() or {}
    detail = row.get("detail") or {}
    check(
        detail.get("phase") == "theory" and detail.get("teachable") == PS, f"C3: {row}"
    )
    shot = world.dir / "theory.png"
    check(shot.exists() and shot.stat().st_size > PAINTED, "screenshot never painted")
    return (
        f"armed, card {screen['unit']} learn={view['learn_target'][1]}; "
        f"C3 signed theory {PS}; {shot}"
    )


def case_b(world: World) -> str:
    """Signed teaching minutes on the unit's module mint theory credits, pay the day."""
    seeded(world)
    world.role("flip", "prefix-sums/0/180")
    need = needed(world)
    world.role(
        "teach",
        f"{ALGO}/stack-queue/{12 * need}/30",
        f"mysql-8-for-timed-sql-coding-tests-joins-and/sql/{12 * need}/29",
        f"{ALGO}/-/{12 * need}/28",
    )
    _, out = world.role("harvest")
    check(not world.entry_ids("theory:"), f"another module or subject minted: {out}")
    world.role(
        "teach", f"{ALGO}/prefix-sums/{12 * need - 5}/20", f"{ALGO}/prefix-sums/5/10"
    )
    _, out = world.role("harvest")
    minted = world.entry_ids("theory:")
    check(len(minted) == need, f"minted {minted} for {need}: {out}")
    check("settled today" in out, f"day not settled: {out}")
    code, log, most = world.lock(seconds=20)
    check(
        code == 0 and most == 0 and "already unlocked" in log,
        f"lock: {code} {most} {log[-600:]}",
    )
    return (
        f"{need} credits ({minted[0]}..{minted[-1]}) in one harvest, settled; "
        "lock windowless; other module/subject/review: 0"
    )


def case_c(world: World) -> str:
    """SOLVE: minutes after the flip mint nothing, no learn control, solves pay."""
    seeded(world)
    world.role("flip", "prefix-sums/0/240", "prefix-sums/1/60")
    need = needed(world)
    world.role("teach", f"{ALGO}/prefix-sums/{12 * need}/10")
    _, out = world.role("harvest")
    check(not world.entry_ids("theory:"), f"minted after the flip: {out}")
    detail = (world.phase_file() or {}).get("detail") or {}
    check(
        detail.get("phase") == "solve" and detail.get("teachable") == [],
        f"C3: {detail}",
    )
    code, log, most = world.lock(seconds=20, until="model.json", shot="solve")
    model = world.model() or {}
    screen, view = model.get("screen") or {}, model.get("view") or {}
    check(code is None and most > 0, f"lock did not arm: {code} {log[-600:]}")
    check(
        screen.get("phase") == "solve" and screen.get("unit_bar"),
        f"no unit bar: {screen}",
    )
    check(
        not screen.get("card") and view.get("learn_target") is None,
        f"learn shown: {screen}",
    )
    shot = world.dir / "solve.png"
    check(shot.exists() and shot.stat().st_size > PAINTED, "screenshot never painted")
    _, out = world.role("harvest", ac="ps-one")
    after = needed(world)
    check(
        "credited 1" in out and after == need - 1, f"solve did not pay: {out} {after}"
    )
    return (
        f"0 minted from {12 * need} min after done; C3 solve []; "
        f"slim bar '{screen['unit_bar']}', no learn; "
        f"solve paid ({need}->{after}); {shot}"
    )


CASES: dict[str, Callable[[World], str]] = {
    "a": case_a,
    "b": case_b,
    "c": case_c,
    "d": case_d,
    "e": case_e,
    "f": case_f,
}


def main(name: str) -> int:
    """Run one case; append its verdict line; exit 0 only on pass."""
    world = World(f"case-{name}")
    try:
        fact, verdict = CASES[name](world), "PASS"
    except AssertionError as failure:
        logging.getLogger(__name__).warning("case %s failed: %s", name, failure)
        fact, verdict = str(failure).splitlines()[0][:300], "FAIL"
    left = world.close()
    if left:
        fact, verdict = f"{fact}; LEFT {left}", "FAIL"
    line = f"{datetime.now(tz=UTC).astimezone().date()} {name} {verdict}: {fact}"
    with (OUT / "results.txt").open("a", encoding="utf-8") as results:
        results.write(line + "\n")
    print(line)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
