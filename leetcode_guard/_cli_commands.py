"""The subcommands that print and exit: probe, status, check, cache, login, sync.

Split out of ``_cli.py`` for the 250-line cap. That module keeps the parser
and the lock command -- the one that opens a window.
"""

from __future__ import annotations

from datetime import datetime, timezone

from leetcode_guard._constants import (
    COOKIES_FILE,
    EXIT_LOCKED,
    EXIT_OK,
    EXIT_UNVERIFIABLE,
    LEDGER_FILE,
    NETWORK_TIMEOUT_SECONDS,
    POOL_CACHE_FILE,
    STATEMENT_CACHE_COUNT,
    STATEMENTS_CACHE_FILE,
    SUGGESTION_COUNT,
)
from leetcode_guard._daycost import local_today, weekday_name
from leetcode_guard._gate import decide
from leetcode_guard._harvest import harvest, needs_seeding
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._login import login
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._settings import build_client
from leetcode_guard._statements import fetch_statements, write_statements
from leetcode_guard._status import format_status, gather_status
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac
from leetcode_guard._sync import sync_ledger


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

    return EXIT_OK if probe.status is ProbeStatus.OK else EXIT_UNVERIFIABLE


def cmd_status() -> int:
    """Print the position from disk. Never touches the network."""
    snapshot = gather_status()
    print(format_status(snapshot))
    return EXIT_LOCKED if snapshot.locked else EXIT_OK


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
    return EXIT_LOCKED if decision.locked else EXIT_OK


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
        return EXIT_LOCKED

    print(f"fetching {len(targets)} statements (one request each)...")
    fetched = fetch_statements(client.post, targets)
    write_statements(STATEMENTS_CACHE_FILE, fetched.statements, fetched_at=now)
    print(f"statements {fetched.reason}")
    print(f"written to {STATEMENTS_CACHE_FILE}")
    return EXIT_OK if fetched.complete else EXIT_LOCKED


def cmd_login() -> int:
    """Store a verified cookie pair. The only flag that writes credentials."""
    ok = login(COOKIES_FILE, timeout=NETWORK_TIMEOUT_SECONDS)
    return EXIT_OK if ok else EXIT_LOCKED


def cmd_sync() -> int:
    """Sync the ledger. Opens no window."""
    result = sync_ledger(LEDGER_FILE)
    print(
        f"sync       {'pushed' if result.pushed else 'not pushed'} -- {result.reason}"
    )
    print(f"records    {result.record_count} total, {result.merged_in} merged in")
    return EXIT_OK if result.pushed else EXIT_LOCKED
