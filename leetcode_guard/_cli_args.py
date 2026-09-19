"""The argument parser, on its own so ``_cli.py`` stays under the line cap.

Subcommand-free by design, matching the sibling lockers: every flag is a
boolean except ``--by``, which qualifies ``--status``.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Define the command line."""
    parser = argparse.ArgumentParser(
        prog="leetcode-guard",
        description="Lock the PC until a LeetCode problem is solved.",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Arm for real: global input grab, VT switching disabled, real ledger.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Print live LeetCode data and exit. Opens no window, writes nothing.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the ledger position from disk. No network, no window, no writes.",
    )
    parser.add_argument(
        "--by",
        metavar="DD.MM.YYYY",
        help=(
            "With --status: also fetch the profile's solved counts and project "
            "how many problems you will have by that date if every gated day "
            "is fed and the debt is cleared. The one network call --status makes."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Print today's full decision trace against live LeetCode data. "
            "Opens no window and writes nothing -- the dry run."
        ),
    )
    parser.add_argument(
        "--cache-statements",
        action="store_true",
        help=(
            "Mirror the top suggestions' problem text for offline reading. "
            "One request per problem, so run it rarely."
        ),
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help=(
            "Store LeetCode cookies, read from stdin and saved only if a live "
            "query proves they work. Re-run when the session expires."
        ),
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Push the ledger to the sync repo and merge other devices in.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log at DEBUG.",
    )
    return parser
