#!/usr/bin/env python3
"""End-to-end for ``--production --evening`` on a private Xvfb (never ``:0``).

Real processes, real Tk, a real X grab; faked only: the LeetCode network, the
HMAC key (a temp file), ``$HOME`` and ``$XDG_RUNTIME_DIR`` (scratch), the
snapshot push and the Firebase sync (see ``e2e_evening_roles``). Run from the
repo root, so ``-m`` puts the checkout (not the editable install) on the path::

    python3 -m scripts.e2e_evening [--only paid|unpaid|end|nox]

Scenarios: ``paid`` (window must never exist, exit 0), ``unpaid`` (window up,
then a signed charge row lands, window gone, exit 0), ``end`` (the control
exits 10), ``nox`` (no display, exit 3 within the bound). Shots and the
verdict go to ``~/data/claude-scratch/e2e/leetcode-guard/evening-<stamp>/``.
The live ledger's mtime is the canary: it must not move.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT: Final = Path(__file__).resolve().parent.parent
OUT: Final = Path.home() / "data/claude-scratch/e2e/leetcode-guard"
LIVE_LEDGER: Final = Path.home() / ".local/share/leetcode_guard/ledger.json"
SCREEN: Final = (3840, 2160)
ROLES: Final = "scripts.e2e_evening_roles"
PAINTED_BYTES: Final = 10_000
"""A painted surface shoots at tens of KB; the bare backdrop is about 1 KB."""
EXIT_ENDED: Final = 10
EXIT_NO_X: Final = 3
NO_X_BOUND_S: Final = 20


class Scenario:
    """One private display, one scratch HOME, one child at a time."""

    def __init__(self, name: str, stamp: str, *, display: bool = True) -> None:
        """Make the scratch HOME and key, and start Xvfb unless ``display`` is off."""
        self.name = name
        self.dir = OUT / f"evening-{stamp}" / name
        home = self.dir / "home"
        (home / ".local/share/leetcode_guard").mkdir(parents=True)
        (home / "run").mkdir(mode=0o700)
        (home / "key").write_bytes(b"e" * 32)
        self.display = ""
        self.xvfb: subprocess.Popen[bytes] | None = None
        if display:
            self._start_xvfb()
        self.env = {
            **os.environ,
            "HOME": str(home),
            "XDG_RUNTIME_DIR": str(home / "run"),
            "E2E_KEY": str(home / "key"),
            # The scratch HOME hides the user site that holds gatelock & co.
            "PYTHONUSERBASE": str(Path.home() / ".local"),
            "DISPLAY": self.display or ":99999",
        }
        self.child: subprocess.Popen[bytes] | None = None

    def _start_xvfb(self) -> None:
        """A private display; ``-displayfd`` picks a free number, never ``:0``."""
        read_fd, write_fd = os.pipe()
        size = f"{SCREEN[0]}x{SCREEN[1]}x24"
        self.xvfb = subprocess.Popen(  # pylint: disable=consider-using-with
            [
                "Xvfb",
                "-displayfd",
                str(write_fd),
                "-screen",
                "0",
                size,
                "-nolisten",
                "tcp",
            ],
            pass_fds=(write_fd,),
            stderr=subprocess.DEVNULL,
        )
        os.close(write_fd)
        self.display = f":{os.read(read_fd, 16).decode().strip()}"
        os.close(read_fd)

    def role(self, *args: str) -> int:
        """Run a role from ``e2e_evening_roles`` to completion; its exit code."""
        command = [sys.executable, "-m", ROLES, *args]
        return subprocess.run(command, cwd=ROOT, env=self.env, check=False).returncode

    def start(self) -> None:
        """Start the real ``--production --evening`` process."""
        command = [sys.executable, "-m", ROLES, "child"]
        self.child = subprocess.Popen(  # pylint: disable=consider-using-with
            command, cwd=ROOT, env=self.env
        )

    def windows(self) -> int:
        """Top-level windows on the private display (0 when none, or no X)."""
        shown = subprocess.run(
            ["xwininfo", "-display", self.display, "-root", "-children"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return sum(1 for line in shown.splitlines() if line.strip().startswith("0x"))

    def wait(self, until: Callable[[], bool], seconds: float) -> bool:
        """Poll ``until`` for up to ``seconds``."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if until():
                return True
            time.sleep(0.4)
        return False

    def shot(self, label: str) -> Path:
        """One screenshot of the private display's root."""
        path = self.dir / f"{label}.png"
        subprocess.run(
            ["import", "-display", self.display, "-window", "root", str(path)],
            check=True,
        )
        return path

    def painted(self, label: str, seconds: float = 40) -> bool:
        """Shoot until the surface has painted (not just the backdrop)."""
        return self.wait(
            lambda: self.shot(label).stat().st_size > PAINTED_BYTES, seconds
        )

    def exit_code(self, seconds: float) -> int | None:
        """The child's exit code, or ``None`` if it is still running."""
        if self.child is None:
            return None
        child = self.child
        self.wait(lambda: child.poll() is not None, seconds)
        return child.returncode

    def close(self) -> None:
        """Stop the child and the display."""
        for proc in (self.child, self.xvfb):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


def _check(results: list[str], *, ok: bool, what: str) -> None:
    results.append(f"{'PASS' if ok else 'FAIL'} {what}")


def paid(sc: Scenario, results: list[str]) -> None:
    """Paid today: exit 0 and no window, ever."""
    sc.role("seed")
    sc.role("pay")
    sc.start()
    code = sc.exit_code(20)
    _check(results, ok=code == 0, what=f"paid: exit 0 (got {code})")
    _check(results, ok=sc.windows() == 0, what="paid: no window on the display")


def unpaid(sc: Scenario, results: list[str]) -> None:
    """Unpaid: window up; a signed charge row lands; window gone, exit 0."""
    sc.role("seed")
    sc.start()
    _check(results, ok=sc.wait(lambda: sc.windows() > 0, 25), what="unpaid: window up")
    _check(results, ok=sc.painted("1-up"), what="unpaid: surface painted")
    _check(results, ok=sc.exit_code(0.1) is None, what="unpaid: still up while unpaid")
    sc.role("pay")
    code = sc.exit_code(20)
    _check(results, ok=code == 0, what=f"unpaid: exit 0 after the charge (got {code})")
    _check(results, ok=sc.windows() == 0, what="unpaid: window gone after credit")


def end(sc: Scenario, results: list[str]) -> None:
    """The end-evening control, clicked on the private display, exits 10."""
    sc.role("seed")
    sc.start()
    _check(results, ok=sc.painted("1-up"), what="end: surface painted")
    x, y = SCREEN[0] - 45, 45
    click = ["xdotool", "mousemove", str(x), str(y), "click", "1"]
    subprocess.run(click, env={**os.environ, "DISPLAY": sc.display}, check=True)
    code = sc.exit_code(20)
    _check(results, ok=code == EXIT_ENDED, what=f"end: exit 10 (got {code})")
    _check(results, ok=sc.windows() == 0, what="end: window gone")


def nox(sc: Scenario, results: list[str]) -> None:
    """No display at all: exit 3 inside the bound."""
    sc.role("seed")
    started = time.monotonic()
    sc.start()
    code = sc.exit_code(30)
    took = time.monotonic() - started
    _check(results, ok=code == EXIT_NO_X, what=f"nox: exit 3 (got {code})")
    _check(results, ok=took < NO_X_BOUND_S, what=f"nox: bounded ({took:.1f} s)")


SCENARIOS: Final = {"paid": paid, "unpaid": unpaid, "end": end, "nox": nox}


def main(argv: list[str]) -> int:
    """Run the scenarios, print PASS/FAIL lines, exit 1 on any FAIL."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    before = LIVE_LEDGER.stat().st_mtime_ns if LIVE_LEDGER.exists() else None
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    results: list[str] = []
    for name, run in SCENARIOS.items():
        if args.only in (None, name):
            sc = Scenario(name, stamp, display=name != "nox")
            try:
                run(sc, results)
            finally:
                sc.close()
    after = LIVE_LEDGER.stat().st_mtime_ns if LIVE_LEDGER.exists() else None
    _check(results, ok=before == after, what="canary: live ledger mtime untouched")
    print("\n".join(results))
    return 1 if any(line.startswith("FAIL") for line in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
