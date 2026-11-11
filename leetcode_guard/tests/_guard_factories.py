"""Build a :class:`LeetcodeGuard` under test.

Everything the lock touches is injected: the executor runs inline so polls are
deterministic and thread-free, the clock is fixed, and the ledger, escape
history and HMAC key all live in ``tmp_path``.
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict, Unpack

from leetcode_guard._auth import AuthState
from leetcode_guard._harvest import SeedStamp, seed_ledger
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps, GuardSeams
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import parse_problem
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._ledger_fixtures import NOW, submission
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

SIGNED_OUT = AuthState(cookies=None, note="signed out")


class InlineExecutor:
    """Runs submitted work immediately on the calling thread."""

    def submit(self, fn, *args, **kwargs) -> Future:
        """Run ``fn`` now and hand back an already-resolved future."""
        future: Future = Future()
        # Deliberately not guarded: the poller has its own crash handling,
        # and swallowing an exception here would hide a broken test helper
        # behind a future that simply never resolves.
        future.set_result(fn(*args, **kwargs))
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Accept the pool's shutdown call; there is no thread to stop."""


def pool_of(*slugs: str) -> PoolResolution:
    """A resolved suggestion list."""
    problems = tuple(
        p for p in (parse_problem(problem_row(slug)) for slug in slugs) if p is not None
    )
    return PoolResolution(problems=problems, source="cache", notes=("pool note",))


def probe_of(*ids: str) -> SolveProbe:
    """An OK probe carrying the given submission ids."""
    return SolveProbe(
        status=ProbeStatus.OK,
        submissions=tuple(submission(item) for item in ids),
        reason=f"{len(ids)} recent",
    )


UNVERIFIABLE = SolveProbe(
    status=ProbeStatus.UNVERIFIABLE, submissions=(), reason="cannot reach LeetCode"
)


class GuardOptions(TypedDict, total=False):
    """The keyword options :func:`create_guard` takes; all are optional."""

    demo_mode: bool
    probe: SolveProbe | None
    poll_probe: SolveProbe | None
    pool: PoolResolution | None
    key_file: Path | None
    write_ledger: bool
    wait_turn: bool
    now: datetime
    seeded: bool


def create_guard(
    tmp_path: Path, **options: Unpack[GuardOptions]
) -> tuple[LeetcodeGuard, dict[str, Any]]:
    """Build a guard plus a record of what its fake network was asked.

    Args:
        tmp_path: Per-test directory for the ledger and escape history.
        **options: Any of the keys below, each with the default shown.
        demo_mode: Which lock configuration to arm with. Defaults to True.
        probe: The startup probe, used for seeding.
        poll_probe: What each subsequent poll returns. Defaults to ``probe``.
        pool: The suggestion list.
        key_file: HMAC key. ``None`` (the default) means integrity checking
            is off.
        write_ledger: Whether the guard may persist anything. Defaults to
            True.
        wait_turn: Whether the guard waits its turn. Defaults to True.
        now: Fixed clock. Defaults to ``NOW``.
        seeded: Pre-seed the ledger on an earlier day, so the guard starts on
            an ordinary gating day. Seeding settles the day it runs on, so a
            guard that seeds itself is by definition unlocked -- any test about
            locked behaviour wants this. The seed lands on the preceding
            *Friday* rather than the day before, because ``NOW`` is a Monday and
            a Sunday seed would settle a weekend day at double cost, making
            every balance in every test two off for no reason anyone reading it
            would guess. Defaults to False.

    Returns:
        The guard and a dict recording every network call.
    """
    now = options.get("now", NOW)
    key_file = options.get("key_file")
    probe = options.get("probe")
    startup = probe if probe is not None else probe_of()
    if options.get("seeded", False):
        seed_ledger(
            Ledger(),
            startup,
            stamp=SeedStamp(
                day=now.date() - timedelta(days=3), now=now, key_file=key_file
            ),
            path=tmp_path / "ledger.json",
        )
    poll_probe = options.get("poll_probe")
    polled = poll_probe if poll_probe is not None else startup
    calls: dict[str, Any] = {"posts": 0}
    pool = options.get("pool")

    def post(_query: str, _variables: dict[str, Any]) -> Any:
        calls["posts"] += 1

    guard = LeetcodeGuard(
        demo_mode=options.get("demo_mode", True),
        deps=GuardDeps(
            ledger_path=tmp_path / "ledger.json",
            escape_path=tmp_path / "escape.json",
            post=post,
            username="kuchy",
            auth=SIGNED_OUT,
            # Deliberately *not* ``two-sum``, which is what ``submission``
            # defaults to: the lock now filters the displayed list against the
            # probe, so a pool whose only problem is the one the startup probe
            # reports as solved renders empty -- which is correct behaviour and
            # an unrealistic fixture. The real pool is resolved after that
            # probe and already excludes it (see ``cmd_lock``).
            pool=pool if pool is not None else pool_of("add-two-numbers"),
            probe=startup,
            key_file=key_file,
            write_ledger=options.get("write_ledger", True),
            seams=GuardSeams(
                wait_turn=options.get("wait_turn", True),
                executor=InlineExecutor(),
                now=lambda: now,
            ),
        ),
    )
    # The poller's work function is the only thing that would really call the
    # network; swap it for the scripted probe so tests drive the loop by hand.
    guard.check = lambda: polled
    return guard, calls


def guard_with_fresh_solves(
    tmp_path: Path, key_file: Path, **options: Unpack[GuardOptions]
) -> LeetcodeGuard:
    """A seeded guard (``old-1`` already seen) whose polls bring two new solves.

    Args:
        tmp_path: Per-test directory for the ledger and escape history.
        key_file: The HMAC key.
        **options: Further :func:`create_guard` options.

    Returns:
        The guard; two fresh solves are what a seeded Monday needs to unlock.
    """
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        poll_probe=probe_of("brand-new", "also-new", "old-1"),
        key_file=key_file,
        seeded=True,
        **options,
    )
    return guard


def guard_with_one_new_solve(
    tmp_path: Path, **options: Unpack[GuardOptions]
) -> LeetcodeGuard:
    """An unseeded guard that starts having seen ``old`` and then polls ``new``.

    Args:
        tmp_path: Per-test directory for the ledger and escape history.
        **options: Further :func:`create_guard` options.

    Returns:
        The guard.
    """
    guard, _ = create_guard(
        tmp_path, probe=probe_of("old"), poll_probe=probe_of("new", "old"), **options
    )
    return guard
