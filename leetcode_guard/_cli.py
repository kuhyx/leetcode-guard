"""Command-line entry point.

Subcommand-free by design, matching the sibling lockers: bare invocation opens
a demo lock, ``--production`` opens the real one, and the remaining flags are
diagnostics that never open a window and never write state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys
from typing import Final

from leetcode_guard._constants import (
    DEMO_ESCAPE_HISTORY_FILE,
    DEMO_LEDGER_FILE,
    ESCAPE_HISTORY_FILE,
    GATE_START_DATE,
    INSTANCE_LOCK_FILE,
    LEDGER_FILE,
    POOL_CACHE_FILE,
    STATEMENT_CACHE_COUNT,
    STATEMENTS_CACHE_FILE,
    SUGGESTION_COUNT,
)
from leetcode_guard._daycost import local_today, weekday_name
from leetcode_guard._gate import decide
from leetcode_guard._harvest import harvest, needs_seeding, seed_ledger
from leetcode_guard._instance import acquire as acquire_instance
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._lock import GuardDeps, LeetcodeGuard
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._settings import build_client
from leetcode_guard._statements import fetch_statements, write_statements
from leetcode_guard._status import format_status, gather_status
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac
from leetcode_guard._sync import sync_ledger

_EXIT_OK: Final = 0
_EXIT_LOCKED: Final = 1
_EXIT_UNVERIFIABLE: Final = 2


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


def _format_timestamp(seconds: int) -> str:
    """Render a submission timestamp in local time."""
    moment = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone()
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def cmd_probe() -> int:
    """Show what the gate currently sees. Read-only.

    This is the first checkpoint of the build and stays useful afterwards: it
    exercises the exact queries, parsing and ranking the lock depends on,
    without any of the window machinery.
    """
    client = build_client()
    print(f"username: {client.username}")
    print(f"auth:     {client.auth.note}")

    probe = fetch_recent_ac(client.post, client.username)
    print(f"\nprobe:    {probe.status.value} -- {probe.reason}")
    for submission in probe.submissions:
        print(
            f"  {_format_timestamp(submission.timestamp)}  "
            f"{submission.title_slug} ({submission.lang}) "
            f"id={submission.submission_id}"
        )

    now = datetime.now(tz=timezone.utc).timestamp()
    pool = resolve_pool(
        client.post,
        POOL_CACHE_FILE,
        now=now,
        solved=SolvedKnowledge(
            auth=client.auth, slugs=solved_slugs(load_ledger(LEDGER_FILE))
        ),
    )
    print(f"\npool:     {len(pool.problems)} problems from {pool.source}")
    for note in pool.notes:
        print(f"  note: {note}")
    print(f"\ntop {SUGGESTION_COUNT} suggestions:")
    for index, problem in enumerate(pool.problems[:SUGGESTION_COUNT], start=1):
        print(
            f"  {index:2d}. {problem.title} "
            f"-- {problem.difficulty} - {problem.ac_rate:.1f}% acceptance"
        )
        print(f"      {problem.url}")

    return _EXIT_OK if probe.status is ProbeStatus.OK else _EXIT_UNVERIFIABLE


def cmd_status() -> int:
    """Print the position from disk. Never touches the network."""
    snapshot = gather_status()
    print(format_status(snapshot))
    return _EXIT_LOCKED if snapshot.locked else _EXIT_OK


def cmd_check() -> int:
    """Print today's decision against live data, writing nothing.

    The dry run: it does exactly what an armed gate would do, right up to the
    point of persisting anything. Use it to answer "would this lock me out?"
    without finding out the hard way.
    """
    client = build_client()
    now = datetime.now().astimezone()
    day = local_today(now=now)

    ledger = load_ledger(LEDGER_FILE)
    seeding = needs_seeding(ledger)
    print(f"ledger     {len(ledger.entries)} entries from {LEDGER_FILE}")
    print(f"integrity  {'on' if ledger.integrity_ok else 'OFF (key unreadable)'}")

    probe = fetch_recent_ac(client.post, client.username)
    print(f"probe      {probe.status.value} -- {probe.reason}")

    result = harvest(ledger, probe, day=day, now=now)
    if seeding:
        # Seeding always runs before the first harvest does, so printing the
        # raw harvest count here would promise credits that will never exist.
        print(
            f"seeding    first run: {len(probe.submissions)} existing "
            "submissions would be marked already-seen"
        )
        print("harvest    would mint 0 credits (seeding claims them all)")
    else:
        print(
            f"harvest    would mint {result.gained} credits "
            f"({result.already_known} known)"
        )

    decision = decide(ledger, day=day, now=now)
    print(
        f"balance    {decision.balance.credits} earned "
        f"- {decision.balance.charged} spent = {decision.balance.available}"
    )
    print(f"today      {day} ({weekday_name(day)}) costs {decision.cost}")
    print(f"decision   {decision.state.value} -- {decision.reason}")
    if decision.needed:
        print(f"needed     {decision.needed} more")
    print("\n(nothing was written)")
    return _EXIT_LOCKED if decision.locked else _EXIT_OK


def cmd_cache_statements() -> int:
    """Mirror problem statements so the lock is usable with no network."""
    client = build_client()
    now = datetime.now(tz=timezone.utc).timestamp()
    pool = resolve_pool(
        client.post,
        POOL_CACHE_FILE,
        now=now,
        solved=SolvedKnowledge(
            auth=client.auth, slugs=solved_slugs(load_ledger(LEDGER_FILE))
        ),
    )
    targets = pool.problems[:STATEMENT_CACHE_COUNT]
    if not targets:
        print("no problems to cache -- refresh the pool first (--probe)")
        return _EXIT_LOCKED

    print(f"fetching {len(targets)} statements (one request each)...")
    fetched = fetch_statements(client.post, targets)
    write_statements(STATEMENTS_CACHE_FILE, fetched.statements, fetched_at=now)
    print(f"statements {fetched.reason}")
    print(f"written to {STATEMENTS_CACHE_FILE}")
    return _EXIT_OK if fetched.complete else _EXIT_LOCKED


def cmd_sync() -> int:
    """Sync the ledger. Opens no window."""
    result = sync_ledger(LEDGER_FILE)
    print(
        f"sync       {'pushed' if result.pushed else 'not pushed'} -- {result.reason}"
    )
    print(f"records    {result.record_count} total, {result.merged_in} merged in")
    return _EXIT_OK if result.pushed else _EXIT_LOCKED


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
        return _EXIT_OK
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
        return _EXIT_OK

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
        return _EXIT_OK

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
        return _EXIT_OK

    pool = resolve_pool(
        client.post,
        POOL_CACHE_FILE,
        now=now.timestamp(),
        solved=SolvedKnowledge(auth=client.auth, slugs=solved_slugs(ledger)),
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
    return _EXIT_OK


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
    if args.sync:
        return cmd_sync()
    if args.cache_statements:
        return cmd_cache_statements()
    return cmd_lock(demo_mode=not args.production)
