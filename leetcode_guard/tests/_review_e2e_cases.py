"""The scenarios of ``scripts/verify_review_first``, one world each.

Each takes the scratch base dir and returns ``(label, ok)`` claims. A lock that
never arms ends its scenario at once (one FAIL, no further waits), so a broken
build fails inside the run's budget instead of at the watchdog.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Final

import earned_time

from leetcode_guard.tests._review_e2e import ALGO, MODULE, State, World

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

Claims = list[tuple[str, bool]]

_logger: Final = logging.getLogger(__name__)
ARM_SECONDS: Final = 15.0
"""A lock arms in 2-3 s here; far past that it never will."""
SWAP_BOUND: Final = 1.5
"""Seconds from the tutor's rename to the swapped rows on screen: the watch's
1 s stat period plus one poll. Each rep renames at a different phase of that
period; measured 2026-11-22: 0.18 to 1.06 s. A rename just after a stat waits
the whole second, so "under 1 s" was never a property, only a lucky phase."""
SWAP_REPS: Final = 3
SETTLE_SECONDS: Final = 2.5
"""Real time before "STAYS released": 2.5 ``recovery_tick_ms`` (1 s) ticks."""
FALLBACK_SECONDS: Final = 5.0
PRESS_SETTLE_SECONDS: Final = 1.0
WORLDS: list[World] = []
REVIEW_GLYPH: Final = "\N{CLOCKWISE OPEN CIRCLE ARROW}"


def is_review(st: State) -> bool:
    """One row, the review row."""
    rows = st["rows"]
    return len(rows) == 1 and str(rows[0]).startswith(REVIEW_GLYPH)


def is_solve(st: State) -> bool:
    """Problem rows, none of them the review row."""
    rows = st["rows"]
    return len(rows) >= 2 and not any(str(r).startswith(REVIEW_GLYPH) for r in rows)


def summary(st: State | None) -> str:
    """One line per state, for a failure report."""
    if st is None:
        return "no state"
    keys = ("grab", "study", "strip", "reads", "status", "learn")
    return f"rows={st['rows'][:2]} " + " ".join(f"{k}={st.get(k)}" for k in keys)


def due_doc(world: World, due_ms: list[int], *, seq: int) -> str:
    """``review_due.json`` with one row signed the way the tutor signs."""
    detail = {
        "subject": ALGO,
        "module": MODULE,
        "due_ms": due_ms,
        "at": time.time(),
    }
    row: dict[str, object] = {
        "kind": "review_due",
        "entry_id": f"due:{ALGO}:{MODULE}:{seq}",
        "day": time.strftime("%Y-%m-%d"),
        "detail": detail,
    }
    row["hmac"] = earned_time.entry_signature(row, (world.dir / "key").read_bytes())
    return json.dumps({"version": 1, "entries": [row]})


def put_due(world: World, *, due: bool, seq: int) -> float:
    """Replace the file the way the tutor does (rename); the rename's time."""
    now = int(time.time() * 1000)
    ms = [now - 60_000 * i for i in (1, 2, 3)] if due else [now + 3_600_000]
    tmp = world.tutor / "review_due.json.tmp"
    tmp.write_text(due_doc(world, ms, seq=seq), encoding="utf-8")
    os.replace(tmp, world.tutor / "review_due.json")
    return time.time()


def armed(world: World, want: Callable[[State], bool]) -> State | None:
    """The first state that ``want``s within ``ARM_SECONDS``; logs the tail if none."""
    st = world.wait(want, timeout=ARM_SECONDS)
    if st is None:
        tail = world.log.read_text(errors="replace").splitlines()[-15:]
        _logger.warning(
            "%s never armed; last %s", world.dir.name, summary(world.last())
        )
        _logger.warning("its log ends:\n%s", "\n".join(tail))
    return st


def new_world(base: Path, name: str, **fake: str) -> World:
    """A world named ``name`` under ``base``: its Xvfb up, its fakes in place."""
    world = World(base / name)
    WORLDS.append(world)  # the parent closes every world, also on a raise
    world.start_x()
    world.fakebin(**fake)
    return world


def due_and_swap(base: Path) -> Claims:
    """The row shows with the grab held, then swaps both ways on a rename."""
    world = new_world(base, "swap")
    put_due(world, due=True, seq=1)
    world.start_lock()
    st = armed(world, is_review)
    claims = [
        ("due: the review row is the only row", st is not None),
        ("due: the lock holds the grab", bool(st and st["grab"]) and world.grab_held()),
    ]
    if st is None:
        return claims
    lat: list[float] = []
    for seq in range(2, 2 + 2 * SWAP_REPS):
        due = seq % 2 == 1
        time.sleep(0.3 + 0.17 * (seq - 2))  # rename at a different watch phase each rep
        at = put_due(world, due=due, seq=seq)
        hit = world.wait(is_review if due else is_solve, after=at, timeout=8)
        lat.append(hit["t"] - at if hit else float("inf"))
    shown = ", ".join(f"{x:.2f}" for x in lat)
    claims.append(
        (f"swap: SOLVE and back within {SWAP_BOUND} s ({shown})", max(lat) < SWAP_BOUND)
    )
    return claims


def planted(base: Path) -> Claims:
    """An unsigned file is "cannot check": the lock arms on the SOLVE rows."""
    world = new_world(base, "planted")
    bad = '{"version":1,"entries":[{"kind":"review_due","hmac":"\\u00e9"}]}'
    (world.tutor / "review_due.json").write_text(bad, encoding="utf-8")
    world.start_lock()
    st = armed(world, is_solve)
    warned = world.lines("WARNING leetcode_guard._review_due")
    return [
        (
            "planted: the lock arms on the SOLVE rows",
            st is not None and bool(st["grab"]),
        ),
        (f"planted: one warning ({len(warned)})", len(warned) == 1),
    ]


def demo(base: Path) -> Claims:
    """The demo shows its fixture and never reads the tutor's file."""
    world = new_world(base, "demo")
    put_due(world, due=True, seq=1)
    world.start_lock("demo", extra={"LEETCODE_GUARD_DEMO_PHASE": "solve"})
    st = armed(world, is_solve)
    time.sleep(1.5)
    reads = [s["reads"] for s in world.states()]
    return [
        ("demo: shows the SOLVE rows", st is not None),
        (
            f"demo: read review_due.json {max(reads, default=0)} times",
            st is not None and set(reads) == {0},
        ),
    ]
