"""The argument parser and the one-shot dispatch, apart for ``_cli.py``'s line cap.

Subcommand-free by design, matching the sibling lockers: every flag is a
boolean except ``--by``, which qualifies ``--status``.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from kuhy_credit import credit_line

from leetcode_guard._cli_commands import (
    cmd_cache_statements,
    cmd_check,
    cmd_login,
    cmd_probe,
    cmd_status,
    cmd_sync,
)
from leetcode_guard._cli_difficulty import cmd_backfill_difficulty
from leetcode_guard._flagged_cli import cmd_flagged
from leetcode_guard._postmortem_cli import cmd_postmortem_dry_run
from leetcode_guard._snapshot_push import cmd_push_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable


def build_parser() -> argparse.ArgumentParser:
    """Define the command line."""
    parser = argparse.ArgumentParser(
        prog="leetcode-guard",
        description="Lock the PC until a LeetCode problem is solved.",
        epilog=credit_line(),
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Arm for real: global input grab, VT switching disabled, real ledger.",
    )
    parser.add_argument(
        "--evening",
        action="store_true",
        help=(
            "With --production: one rung of the evening chain. Exits 0 at once "
            "when today's leetcode charge is paid; else locks until it lands. "
            "Exit 10 = evening ended from the window, 3 = no X server."
        ),
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "Print live LeetCode data and exit. Opens no window; "
            "refreshes the pool cache."
        ),
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
        "--price",
        type=int,
        metavar="N",
        help=(
            "With --status: project at this Tue-Thu base price instead of the "
            "live one (Mon/Fri/Sat/Sun cost twice it). Implies --by end of year."
        ),
    )
    parser.add_argument(
        "--goal",
        action="append",
        metavar="DIFFICULTY=N",
        help=(
            "With --status: an absolute solved-count target, e.g. Easy=837; "
            "repeatable. Prints when the price reaches it and the smallest "
            "price that lands it on the --by date. Implies --by end of year."
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
        "--backfill-difficulty",
        action="store_true",
        help=(
            "Write signed difficulty rows for every solved problem that lacks "
            "one (pool cache first, then LeetCode, politely). Credits are "
            "priced Easy 1 / Medium 2 / Hard 4; unknown counts as Easy."
        ),
    )
    parser.add_argument(
        "--max-fetch",
        type=int,
        default=25,
        help="Network lookups per --backfill-difficulty run (default 25).",
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
        "--push-snapshot",
        action="store_true",
        help=(
            "Publish the status app's snapshot to Firebase once and print the "
            "outcome. Display only: refreshes the profile mirror at most every "
            "15 min, never touches the ledger."
        ),
    )
    parser.add_argument(
        "--flagged",
        action="store_true",
        help=(
            "List solves that took over 20 min of active time although their "
            "theory was taught, then a summary. Read-only, no network."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --flagged: print the whole report as one JSON document.",
    )
    parser.add_argument(
        "--postmortem-dry-run",
        metavar="UNIT",
        help=(
            "Run the tutor's post-mortem of UNIT on its solves so far, writing "
            "no card: prints the report, or 'pending' (exit 75): call again."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log at DEBUG.",
    )
    return parser


def chosen_command(args: argparse.Namespace) -> Callable[[], int] | None:
    """The first one-shot command the flags ask for, or ``None`` to lock.

    First match wins, in this order. Built per call, so the commands are looked
    up when ``main`` runs rather than frozen at import.
    """
    commands: tuple[tuple[bool, Callable[[], int]], ...] = (
        (args.probe, cmd_probe),
        (
            args.status,
            lambda: cmd_status(by=args.by, price=args.price, goals=args.goal),
        ),
        (args.check, cmd_check),
        (args.login, cmd_login),
        (args.sync, cmd_sync),
        (args.cache_statements, cmd_cache_statements),
        (
            args.backfill_difficulty,
            lambda: cmd_backfill_difficulty(max_fetch=args.max_fetch),
        ),
        (args.push_snapshot, cmd_push_snapshot),
        (args.flagged, lambda: cmd_flagged(as_json=args.json)),
        (
            bool(args.postmortem_dry_run),
            lambda: cmd_postmortem_dry_run(args.postmortem_dry_run),
        ),
    )
    return next((run for chosen, run in commands if chosen), None)
