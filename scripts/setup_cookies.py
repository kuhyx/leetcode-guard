#!/usr/bin/env python3
"""Write ``cookies.json`` from a logged-in browser session, then prove it works.

Signed out, ``questionList`` cannot filter solved problems, so the lock suggests
problems that were solved weeks ago. That does not break the gate -- credits key
on submission id (``_harvest.py``), so re-solving still mints one -- but it
wastes the grind on work already done.

The two values are read from **stdin, never argv**: a token passed as an
argument lands in shell history and in ``ps`` output for every user on the box.
For the same reason the prompt is silenced with :func:`getpass.getpass` when a
TTY is attached, and the file is created ``0600`` *before* anything is written
into it -- writing first and chmod-ing after leaves a window where the token is
world-readable.

Nothing here is a credit path: this writes an auth file, never the ledger.

Get the values from a browser logged into leetcode.com: DevTools -> Application
-> Cookies -> https://leetcode.com, rows ``LEETCODE_SESSION`` and ``csrftoken``.

Usage -- by path, so it works from any directory::

    python3 ~/leetcode-guard/scripts/setup_cookies.py
    python3 ~/leetcode-guard/scripts/setup_cookies.py --print-path

``python3 -m scripts.setup_cookies`` also works, but *only* from the repo root:
``scripts/`` is not a package (and must not become one), so ``-m`` finds it via
the current directory and nothing else. This is the one script here that is run
by hand from wherever the user happens to be, rather than from a hook with a
known working directory, so the path form is the documented one. The package
itself imports fine from anywhere because it is installed into user
site-packages.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import logging
import sys
from typing import TYPE_CHECKING

from leetcode_guard._auth import CSRF_KEY, SESSION_KEY
from leetcode_guard._constants import COOKIES_FILE, POOL_CACHE_FILE

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# rw for the owner only. The session cookie is a bearer credential: anyone who
# can read it is signed in as kuhy until it expires.
_FILE_MODE = 0o600

# A LeetCode session cookie is a long signed blob; a csrftoken is 32-64 chars.
# This is a fat-finger check (a truncated paste, a stray newline), not
# validation -- only the probe can say whether the value actually authenticates.
_MIN_SESSION_LEN = 20
_MIN_CSRF_LEN = 16


def _read_secret(label: str, *, minimum: int) -> str:
    """Prompt for one cookie value on stdin and sanity-check its length.

    Uses ``getpass`` on a TTY so the token is not echoed to the terminal or
    captured by a scrollback buffer; falls back to a plain read when stdin is a
    pipe, so the script stays usable non-interactively.

    Args:
        label: The cookie name to show in the prompt.
        minimum: Shortest plausible length for this value.

    Returns:
        The entered value, stripped.

    Raises:
        ValueError: If the value is empty or implausibly short.
    """
    prompt = f"{label}: "
    raw = getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline()
    value = raw.strip()
    if not value:
        msg = f"{label} is empty -- nothing written."
        raise ValueError(msg)
    if len(value) < minimum:
        msg = (
            f"{label} is only {len(value)} characters, which is too short to be"
            f" real (expected at least {minimum}). Nothing written -- check for"
            " a truncated paste."
        )
        raise ValueError(msg)
    return value


def write_cookies(session: str, csrf: str, path: Path = COOKIES_FILE) -> Path:
    """Write the cookie file with owner-only permissions.

    The file is created empty at ``0600`` and only then filled, so the token is
    never briefly readable by other users. An existing file is truncated in
    place rather than unlinked, keeping the restrictive mode across a rewrite.

    Args:
        session: The ``LEETCODE_SESSION`` cookie value.
        csrf: The ``csrftoken`` cookie value.
        path: Destination; defaults to the real config location.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create empty, tighten, *then* write: the token must never exist on disk
    # under looser permissions, however briefly. touch(mode=...) alone is not
    # enough -- it is masked by the process umask, and it does nothing at all to
    # an existing file -- so the explicit chmod is what actually guarantees
    # 0600, on both the create and the overwrite path.
    path.touch(mode=_FILE_MODE, exist_ok=True)
    path.chmod(_FILE_MODE)
    payload = {SESSION_KEY: session, CSRF_KEY: csrf}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Write leetcode-guard's cookies.json from stdin.",
    )
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="print the destination path and exit, writing nothing",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    """Prompt for both cookies, write the file, and say what to run next.

    Returns:
        A process exit code.
    """
    args = _parse_args(argv)
    if args.print_path:
        print(COOKIES_FILE)
        return 0

    print("Paste the two cookie values from a browser logged into leetcode.com.")
    print("DevTools -> Application -> Cookies -> https://leetcode.com")
    print("Input is hidden and is never passed on the command line.\n")

    try:
        session = _read_secret(SESSION_KEY, minimum=_MIN_SESSION_LEN)
        csrf = _read_secret(CSRF_KEY, minimum=_MIN_CSRF_LEN)
    except ValueError as exc:
        # A rejected paste is the expected failure, not a crash: report it and
        # exit non-zero so nothing half-written is left behind.
        _logger.warning("cookie input rejected: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except EOFError, KeyboardInterrupt:
        _logger.warning("cookie setup aborted at the prompt; nothing written")
        print("\naborted -- nothing written.", file=sys.stderr)
        return 1

    path = write_cookies(session, csrf)
    print(f"\nwrote {path} (mode 600)")
    print("Now confirm it authenticates:")
    print("    python3 -m leetcode_guard --probe")
    print("'auth:' should no longer say 'Not signed in'.\n")
    # Signing in cannot retroactively filter a pool cached while signed out:
    # solved status is per-row data captured at fetch time, so every cached row
    # reads status=None and the filter has nothing to act on. The cache lives a
    # week, so without this the suggestions keep offering solved problems while
    # announcing that they are hidden.
    print("If you were signed out when the pool was last cached, drop it so the")
    print("next fetch records which problems you have solved:")
    print(f"    rm {POOL_CACHE_FILE}")
    print("    python3 -m leetcode_guard --probe")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
