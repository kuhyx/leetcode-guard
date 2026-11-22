"""Command-line entry point.

Subcommand-free by design, matching the sibling lockers: bare invocation opens
a demo lock, ``--production`` opens the real one, and the remaining flags are
diagnostics that never open a window.

Those diagnostics write nothing, with three deliberate exceptions:
``--cache-statements`` mirrors problem text, ``--login`` stores a verified
cookie pair, and ``--push-snapshot`` publishes the status app's display-only
snapshot (refreshing the profile mirror). Each writes only its own file or
node and none touches the ledger -- no flag here can move the balance or
settle a day.
"""

from __future__ import annotations

from datetime import datetime
import sys

from gatelock import wait_for_x_server

from leetcode_guard import _errors
from leetcode_guard._cli_args import build_parser, chosen_command
from leetcode_guard._constants import (
    DEMO_ESCAPE_HISTORY_FILE,
    DEMO_LEDGER_FILE,
    ESCAPE_HISTORY_FILE,
    EXIT_OK,
    GATE_START_DATE,
    INSTANCE_LOCK_FILE,
    LEDGER_FILE,
    POOL_CACHE_FILE,
    PROGRESS_CACHE_FILE,
)
from leetcode_guard._daycost import local_today
from leetcode_guard._evening import busy_exit, evening_paid, evening_preflight
from leetcode_guard._gate import apply_decision
from leetcode_guard._gate_today import decide_today
from leetcode_guard._harvest import SeedStamp, needs_seeding, seed_ledger
from leetcode_guard._instance import acquire as acquire_instance
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps, GuardSeams
from leetcode_guard._lock_evening import EveningGuard
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._morning_session import defer_for_morning_session
from leetcode_guard._night_lockdown import defer_for_evening_lockdown
from leetcode_guard._nudge_server import NUDGE_PORT
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._progress import refresh_progress
from leetcode_guard._settings import build_client
from leetcode_guard._study_restart import read_marker, resume_study
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac
from leetcode_guard._unit_view import unit_view
from leetcode_guard._x_probe import QuietXProbe


def cmd_lock(*, demo_mode: bool, evening: bool = False) -> int:
    """Arm the gate, opening a window only if today is not already settled.

    Every network call happens here, before any window exists. A fetch on the
    paint path would mean no window when the network is down, and no window is
    the bypass this whole tool exists to close.
    """
    if evening and (early := evening_preflight(LEDGER_FILE)) is not None:
        return early
    if not demo_mode and not evening:
        # Timer catch-up fires before X exists: wait for the server, no
        # clock, before the first fetch, and *before* the instance lock (a
        # holder stalls the harvest all night lockdown; 2026-10-17).
        wait_for_x_server(probe=QuietXProbe())
    instance = acquire_instance(INSTANCE_LOCK_FILE)
    if instance is None:
        # The afternoon retry firing while the morning run is still queued
        # behind the workout lock. Two waiters would clear the gate twice.
        print("another leetcode-guard run is already active", file=sys.stderr)
        return busy_exit(LEDGER_FILE) if evening else EXIT_OK
    try:
        return _run_lock(demo_mode=demo_mode, evening=evening)
    finally:
        instance.release()


def _run_lock(*, demo_mode: bool, evening: bool) -> int:
    """The body of :func:`cmd_lock`, once the single-instance lock is held."""
    if not demo_mode and local_today() < GATE_START_DATE:
        # Before build_client: a not-yet-active gate costs no network. Demo
        # mode ignores the date so the lock can always be shown.
        print(f"gate not active until {GATE_START_DATE}; nothing to do")
        return EXIT_OK

    now = datetime.now().astimezone()
    # Evening runs skip the deferrals below (see _evening): no 0 on unpaid.
    gated = not (demo_mode or evening)
    if gated and (why := defer_for_morning_session(now, wait=True)) is not None:
        # The phone's morning session earned the carrot: no gate until the
        # signed instant. A run deferral, never ledger state -- nothing is
        # written, so the next run (login, 09:30 or 11:00 slot) re-decides.
        print(f"deferred: {why}; not arming this run")
        return EXIT_OK

    client = build_client()
    day = local_today(now=now)

    ledger_path = DEMO_LEDGER_FILE if demo_mode else LEDGER_FILE
    escape_path = DEMO_ESCAPE_HISTORY_FILE if demo_mode else ESCAPE_HISTORY_FILE
    if demo_mode:
        # Reset AND re-seed on every demo run. Reset alone would let the first
        # poll harvest the whole recent feed and unlock instantly, proving
        # nothing; seeded, the demo demands one genuinely fresh solve.
        ledger_path.unlink(missing_ok=True)

    ledger = load_ledger(ledger_path)
    decision = decide_today(ledger, day=day, now=now, demo=demo_mode)
    if not decision.locked and not demo_mode:
        # A day paid from banked credit is only settled once the charge is on
        # disk. Returning without it leaves the bank undebited and the day
        # looking, in hindsight, like one the gate never ran on.
        apply_decision(ledger, decision, ledger_path)
        if not evening or evening_paid(ledger_path, key_file=None, now=now):
            print(f"already unlocked: {decision.reason}")
            return EXIT_OK
    if gated and (why := defer_for_evening_lockdown(now)) is not None:
        # Tonight's lockdown already fired (a late credit may have lifted it):
        # do not lock a finished solve out. After the decision, so a day paid
        # from the bank is still settled; nothing is written here.
        print(f"deferred: {why}; not arming this run")
        return EXIT_OK

    probe = fetch_recent_ac(client.post, client.username)
    if not demo_mode:
        # Mirror the profile's solved counts while the network is already in
        # use, so the status window has a figure to show before it fetches its
        # own. Display only; the gate never reads it.
        refresh_progress(
            client.post, client.username, PROGRESS_CACHE_FILE, now=now.timestamp()
        )

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
    if gated and needs_seeding(ledger) and probe.status is ProbeStatus.OK:
        seed_ledger(ledger, probe, stamp=SeedStamp(day=day, now=now), path=ledger_path)
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

    # After the decision and every deferral: only a run that arms looks.
    resume = gated and read_marker(day)
    guard = (EveningGuard if evening else LeetcodeGuard)(
        demo_mode=demo_mode,
        deps=GuardDeps(
            ledger_path=ledger_path,
            escape_path=escape_path,
            post=client.post,
            username=client.username,
            auth=client.auth,
            pool=pool,
            probe=probe,
            seams=GuardSeams(
                sync_on_close=not demo_mode,
                nudge_port=NUDGE_PORT,
                # Read once per poll (``_lock_phase``), never on the paint path.
                phase=unit_view(ledger_path),
                resume_study=resume,
            ),
        ),
    )
    if resume:
        resume_study(guard)
    guard.run()
    return guard.exit_code if evening else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch.

    Returns:
        A process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.evening and not args.production:
        parser.error("--evening needs --production")
    if args.json and not args.flagged:
        parser.error("--json needs --flagged")
    configure_logging(verbose=args.verbose)
    _errors.install()
    command = chosen_command(args)
    if command is not None:
        return command()
    return cmd_lock(demo_mode=not args.production, evening=args.evening)
