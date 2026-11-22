#!/usr/bin/env python3
"""Drive the lock's X wait against a real X server and let its stderr show.

The 2026-11-22 flood (8378 "Authorization required" lines in 70 minutes) came
from libX11 writing to fd 2, which no mock can reproduce. This runs exactly the
wait ``cmd_lock`` runs, ``gatelock.wait_for_x_server`` with the guard's
``QuietXProbe``, and nothing after it: no instance lock, no ledger, no window.
``--base`` uses gatelock's default probe instead, which is the old behaviour.

    Xvfb :87 -auth /tmp/xauth &      # refuses anyone without the cookie
    DISPLAY=:87 XAUTHORITY=/dev/null python3 scripts/verify_x_wait_log.py --seconds 30
    DISPLAY=:87 XAUTHORITY=/tmp/xauth python3 scripts/verify_x_wait_log.py

Count the stderr lines: one refusal plus a heartbeat per 300 s, against two
per second on ``--base``. The last stdout line is ``answered=<bool> waited_s=<s>``.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import gatelock

from leetcode_guard._x_probe import QuietXProbe


def main(argv: list[str]) -> int:
    """Exit 0 when the X server answered, 1 when ``--seconds`` ran out."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--base", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    started = time.monotonic()
    answered = gatelock.wait_for_x_server(
        timeout_s=args.seconds, probe=None if args.base else QuietXProbe()
    )
    waited = time.monotonic() - started
    sys.stdout.write(f"answered={answered} waited_s={waited:.1f}\n")
    return 0 if answered else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
