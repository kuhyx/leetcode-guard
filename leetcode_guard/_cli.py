"""Command-line entry point.

Subcommand-free by design, matching the sibling lockers: bare invocation opens
a demo lock, ``--production`` opens the real one, and the remaining flags are
diagnostics that never open a window.

Those diagnostics write nothing, with two deliberate exceptions:
``--cache-statements`` mirrors problem text, and ``--login`` stores a verified
cookie pair. Both write only their own file and neither touches the ledger --
no flag here can move the balance or settle a day.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys

from leetcode_guard._cli_commands import (
    cmd_cache_statements,
    cmd_check,
    cmd_login,
    cmd_probe,
    cmd_status,
    cmd_sync,
)
from leetcode_guard._constants import (
    DEMO_ESCAPE_HISTORY_FILE,
    DEMO_LEDGER_FILE,
    ESCAPE_HISTORY_FILE,
    EXIT_OK,
    GATE_START_DATE,
    INSTANCE_LOCK_FILE,
    LEDGER_FILE,
    POOL_CACHE_FILE,
)
from leetcode_guard._daycost import local_today
from leetcode_guard._gate import decide
from leetcode_guard._harvest import needs_seeding, seed_ledger
from leetcode_guard._instance import acquire as acquire_instance
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._lock import GuardDeps, LeetcodeGuard
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._settings import build_client
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac


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


def cmd_lock(*, demo_mode: bool) -> int:
    """Arm the gate, opening a window only if today is not already settled.

    Every network call happens here, before any window exists. A fetch on the
    paint path would mean no window when the network is down, and no window is
    the bypass this whole tool exists to close.
    """
    instance = acquire_instance(INSTANCE_LOCK_FILE)
    if instance is None:
        # The afternoon retry firing while the morning run is still queued
        # behind the workout lock. Two waiters would clear the gate twice.
        print("another leetcode-guard run is already active", file=sys.stderr)
        return EXIT_OK
    try:
        return _run_lock(demo_mode=demo_mode)
    finally:
        instance.release()


def _run_lock(*, demo_mode: bool) -> int:
    """The body of :func:`cmd_lock`, once the single-instance lock is held."""
    if not demo_mode and local_today() < GATE_START_DATE:
        # Checked before build_client so a not-yet-active gate costs no network
        # at all -- the timer fires daily from install day and must be free
        # until it is genuinely in force. Demo mode ignores the date so the
        # lock can always be shown.
        print(f"gate not active until {GATE_START_DATE}; nothing to do")
        return EXIT_OK

    client = build_client()
    now = datetime.now().astimezone()
    day = local_today(now=now)

    ledger_path = DEMO_LEDGER_FILE if demo_mode else LEDGER_FILE
    escape_path = DEMO_ESCAPE_HISTORY_FILE if demo_mode else ESCAPE_HISTORY_FILE
    if demo_mode:
        # Reset AND re-seed on every demo run. Reset alone would let the first
        # poll harvest the whole recent feed and unlock instantly, proving
        # nothing; seeded, the demo demands one genuinely fresh solve.
        ledger_path.unlink(missing_ok=True)

    ledger = load_ledger(ledger_path)
    decision = decide(ledger, day=day, now=now)
    if not decision.locked and not demo_mode:
        print(f"already unlocked: {decision.reason}")
        return EXIT_OK

    probe = fetch_recent_ac(client.post, client.username)

    # The run that *creates* the ledger does not arm. Seeding marks the whole
    # recent feed already-seen, so the gate it hands over can only be satisfied
    # by a solve that has not happened yet -- and on 2026-08-05 that gate armed
    # at the same moment the lock removed the browser needed to produce one.
    #
    # Deferring here rather than by writing a charge is deliberate. An earlier
    # fix settled the day in the ledger instead, which meant `rm ledger.json`
    # produced an unlocked day, repeatably: the deferral was expressible as
    # exactly the state `decide` unlocks on. Skipping the run leaves no such
    # state behind -- delete the ledger and you skip one run, you do not earn a
    # day.
    if not demo_mode and needs_seeding(ledger) and probe.status is ProbeStatus.OK:
        seed_ledger(ledger, probe, day=day, now=now, path=ledger_path, key_file=None)
        print("seeded a new ledger; not arming this run -- the next one gates")
        return EXIT_OK

    pool = resolve_pool(
        client.post,
        POOL_CACHE_FILE,
        now=now.timestamp(),
        solved=SolvedKnowledge(
            auth=client.auth,
            # The probe is unioned in rather than relying on the ledger alone.
            # It is the same recent-AC feed the ledger is built from, but it
            # was fetched seconds ago and needs no cookies, so it covers the
            # window between the last harvest and now. It also carries the demo
            # on its own: the demo deletes its ledger every run to force a
            # fresh solve, which left `solved_slugs` empty and put two
            # already-solved problems back at the top of the demo surface.
            slugs=solved_slugs(ledger)
            | frozenset(item.title_slug for item in probe.submissions),
        ),
    )

    guard = LeetcodeGuard(
        demo_mode=demo_mode,
        deps=GuardDeps(
            ledger_path=ledger_path,
            escape_path=escape_path,
            post=client.post,
            username=client.username,
            auth=client.auth,
            pool=pool,
            probe=probe,
            sync_on_close=not demo_mode,
        ),
    )
    guard.run()
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch.

    Returns:
        A process exit code.
    """
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    if args.probe:
        return cmd_probe()
    if args.status:
        return cmd_status()
    if args.check:
        return cmd_check()
    if args.login:
        return cmd_login()
    if args.sync:
        return cmd_sync()
    if args.cache_statements:
        return cmd_cache_statements()
    return cmd_lock(demo_mode=not args.production)
