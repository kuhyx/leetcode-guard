#!/usr/bin/env python3
"""Prove the review-first row end to end: the real lock, real Tk, real X.

The unit tests mock the root, so they cannot show that the row is on the
screen, that the 1 s file watch really brings the swap forward under the
production 30 s poll, or that a press really releases the grab::

    xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_review_first

Each scenario is a world of its own (``leetcode_guard/tests/_review_e2e.py``:
scratch HOME and key, a private Xvfb, fake tutor and ``systemd-run``), all run
at the same time, each lock being ``scripts.verify_review_first_child``:

- due: the review row shows, the grab is held;
- swap: the tutor renames a new ``review_due.json`` in; the rows swap to SOLVE
  and back, each within ``SWAP_BOUND`` of the rename;
- planted: an unsigned file still arms the lock, on the SOLVE rows, one warning;
- spawn fails: the launcher cannot be started; the SOLVE rows come back, grab held;
- launch: the tutor is called on the review route, study mode, the grab is
  released and STAYS released past a recovery tick;
- demo: the demo never reads the tutor's file.
- exits 1: the review's and the learn button's launcher start, then exit 1;
  study mode ends, the grab is back, the marker gone, the failure shows;
- slow ok: a launcher that exits 0 after 3 s keeps study mode.

The scenarios live in ``leetcode_guard/tests/_review_e2e_{cases,press}.py`` (scripts
cannot import scripts). ``xvfb-run`` only provides the non-``:0`` guard; every
lock gets its own display. A watchdog kills everything by PID at
:data:`WATCHDOG_SECONDS`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard.tests._review_e2e_cases import WORLDS
from leetcode_guard.tests._review_e2e_press import SCENARIOS

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard.tests._review_e2e_cases import Claims

_logger: Final = logging.getLogger(__name__)
WATCHDOG_SECONDS: Final = 50.0


def _watchdog() -> None:
    def fire() -> None:
        print(
            f"FAILED: watchdog at {WATCHDOG_SECONDS} s; killing every child", flush=True
        )
        for world in WORLDS:
            world.close()
        os._exit(3)

    timer = threading.Timer(WATCHDOG_SECONDS, fire)
    timer.daemon = True
    timer.start()


def _run(base: Path, scenario: Callable[[Path], Claims]) -> Claims:
    try:
        return scenario(base)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.exception("scenario %s raised", scenario.__name__)
        return [(f"{scenario.__name__}: raised {exc!r}", False)]


def main() -> int:
    """Run every scenario at once; one PASS/FAIL line per claim."""
    if os.environ.get("DISPLAY", ":0") == ":0":
        print("refusing to run on display :0; use xvfb-run", flush=True)
        return 2
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    _watchdog()
    started = time.monotonic()
    base = Path(tempfile.mkdtemp(prefix="lg-review-first-"))
    print(
        "Verifying review first (real lock, real Tk, one Xvfb per scenario):",
        flush=True,
    )
    try:
        with ThreadPoolExecutor(max_workers=len(SCENARIOS)) as pool:
            results = list(pool.map(lambda s: _run(base, s), SCENARIOS))
    finally:
        for world in WORLDS:
            world.close()
    claims = [c for group in results for c in group]
    for label, ok in claims:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}", flush=True)
    failed = sum(not ok for _, ok in claims)
    took = time.monotonic() - started
    if failed:
        print(
            f"\nFAILED: {failed} of {len(claims)} ({took:.1f} s); scratch kept: {base}",
            flush=True,
        )
        return 1
    shutil.rmtree(base, ignore_errors=True)
    print(f"\nOK: {len(claims)} checks passed ({took:.1f} s).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
