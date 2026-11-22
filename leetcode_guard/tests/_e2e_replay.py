"""Case g of ``scripts/e2e_theory``: kuhy's real state, replayed on base and new.

Read-only on the originals: the guard's data dir, the free/sick/focus pools,
the tutor's signed ledger and the shared HMAC key are COPIED into the case's
scratch ``$HOME`` and only the copy is ever opened for anything else. The
canary proves it: the originals the new code could write (``ledger.json``,
``theory_phase.json``, ``module_state.json``) must not be newer than the stamp
taken before the copy. Live units rewrite their own locks and caches all day,
so those are listed, not judged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._pool_cache import read_cache, write_cache
from leetcode_guard.tests._e2e_theory_cases import check
from leetcode_guard.tests._e2e_world import ROOT

if TYPE_CHECKING:
    from leetcode_guard.tests._e2e_world import World

REAL_KEY: Final = Path("/etc/workout-locker/hmac.key")
SHARE: Final = Path.home() / ".local/share"
GUARD: Final = SHARE / "leetcode_guard"
TUTOR_LEDGER: Final = SHARE / "tutor/ledger.json"
PENALTY: Final = Path.home() / ".local/state/wake_alarm/workday_penalty.json"
POOLS: Final = ("freedays", "sickdays", "focus_project")
GUARDED: Final = ("ledger.json", "theory_phase.json", "module_state.json")
DAYS: Final = 14
WORKER: Final = "scripts/e2e_replay_worker.py"


class SkipError(Exception):
    """The real state is absent: the case skips loudly and exits 0."""

    def __init__(self, missing: Path) -> None:
        """Name the missing original."""
        super().__init__(f"no real state: {missing} is absent")


def _guarded() -> list[Path]:
    """Originals the code under test could write."""
    found = [GUARD / name for name in GUARDED]
    return [*found, SHARE / "tutor/module_state.json", TUTOR_LEDGER]


def _stamp(world: World) -> Path:
    """The canary stamp, taken before the first original is read."""
    stamp = world.dir / "canary-stamp"
    stamp.touch()
    os.utime(stamp)
    return stamp


def copy_real(world: World) -> Path:
    """Copy the real state into the world's scratch ``$HOME``; return the stamp."""
    for needed in (REAL_KEY, GUARD / "ledger.json", TUTOR_LEDGER):
        if not needed.exists():
            raise SkipError(needed)
    stamp = _stamp(world)
    skip = shutil.ignore_patterns("venv", "*.lock", "*.tmp", "e2e")
    shutil.copytree(GUARD, world.data, ignore=skip, dirs_exist_ok=True)
    for pool in POOLS:
        if (SHARE / pool).exists():
            shutil.copytree(
                SHARE / pool, world.home / ".local/share" / pool, ignore=skip
            )
    world.tutor.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TUTOR_LEDGER, world.tutor / "ledger.json")
    if PENALTY.exists():
        target = world.home / ".local/state/wake_alarm"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PENALTY, target)
    (world.dir / "key").write_bytes(REAL_KEY.read_bytes())
    _sign_pool_copy(world)
    return stamp


def _sign_pool_copy(world: World) -> None:
    """Sign the COPIED pool cache the way the first refresh after deploy does.

    The real cache predates signing, and an unsigned pool is "cannot check" by
    design; the copy stands for the state once ``--probe`` (or the next arming
    run) has rewritten it. Content, stamp and ``complete`` are kept as they are.
    """
    path = world.data / "pool_cache.json"
    pool = read_cache(path)
    if pool is not None:
        write_cache(path, pool, key_file=world.dir / "key")


def canary(stamp: Path) -> tuple[list[str], list[str]]:
    """(guarded originals newer than the stamp, other files newer: live churn).

    Two levels under each data dir, like ``find -maxdepth 2 -newer``.
    """
    mark = stamp.stat().st_mtime_ns
    guarded = {path.resolve() for path in _guarded()}
    hit: list[str] = []
    churn: list[str] = []
    for top in (GUARD, SHARE / "tutor"):
        for path in [*top.glob("*"), *top.glob("*/*")]:
            if path.is_file() and path.stat().st_mtime_ns > mark:
                (hit if path.resolve() in guarded else churn).append(str(path))
    return hit, churn


def _worker(world: World, tree: Path) -> list[dict[str, object]]:
    """The 14-day decisions of ``tree``'s code on the copy (a fresh process)."""
    env = {k: v for k, v in os.environ.items() if k not in {"DISPLAY", "PYTHONPATH"}}
    env |= {"HOME": str(world.home), "PYTHONPATH": str(tree), "TMPDIR": "/var/disktmp"}
    env["PYTHONUSERBASE"] = str(Path.home() / ".local")
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / WORKER),
            str(tree),
            str(REAL_KEY),
            str(DAYS),
        ],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=50,
    )
    check(done.returncode == 0, f"worker on {tree.name}: {done.stderr[-400:]}")
    return [json.loads(line) for line in done.stdout.splitlines()]


def replay(world: World, base: Path, new: Path) -> str:
    """Decisions of both trees on the same copy; any difference fails."""
    check(base.exists(), f"no base worktree at {base}")
    old, now = _worker(world, base), _worker(world, new)
    check(len(old) == len(now) == 2 * DAYS, f"rows: base {len(old)} new {len(now)}")
    lines = [
        f"{r['day']} {r['view']:<7} {r['state']:<26} cost={r['cost']} needed={r['needed']} "
        f"avail={r['available']} credits={r['credits']} debt={r['debt_owed']}-{r['debt_repaid']}"
        for r in now
    ]
    (world.dir / "replay.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    differ = [
        f"{a['day']} {a['view']}" for a, b in zip(old, now, strict=True) if a != b
    ]
    check(not differ, f"base and new differ on {differ}: see {world.dir}/replay.txt")
    locked = sum(1 for r in now if r["locked"])
    return (
        f"{DAYS} days x morning/evening identical base vs new ({locked} locked views)"
    )


def status_pair(world: World) -> str:
    """``--status`` without, then with, a C2 file saying prefix-sums is not done."""
    code, plain = world.role("status")
    (world.dir / "status-1.txt").write_text(plain, encoding="utf-8")
    check(
        "could not check" in plain, f"plain copy: no 'could not check': {plain[-500:]}"
    )
    check(not (world.tutor / "module_state.json").exists(), "status wrote C2")
    check(code in {0, 1}, f"plain copy exit {code}")
    world.role("flip", "prefix-sums/0/60")
    code, signed = world.role("status")
    (world.dir / "status-2.txt").write_text(signed, encoding="utf-8")
    unit = [row for row in signed.splitlines() if row.startswith("unit ")]
    check(
        unit and unit[0].split()[1:3] == ["prefix-sums", "--"] and "theory" in unit[0],
        f"signed C2: {unit} {signed[-500:]}",
    )
    return f"--status exit {code}; plain: could not check; with C2: {unit[0]}"
