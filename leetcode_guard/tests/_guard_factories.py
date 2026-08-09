"""Build a :class:`LeetcodeGuard` under test.

Everything the lock touches is injected: the executor runs inline so polls are
deterministic and thread-free, the clock is fixed, and the ledger, escape
history and HMAC key all live in ``tmp_path``.
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from leetcode_guard._auth import AuthState
from leetcode_guard._harvest import seed_ledger
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._lock import GuardDeps, LeetcodeGuard
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
        future: Future = Future()
        # Deliberately not guarded: the poller has its own crash handling,
        # and swallowing an exception here would hide a broken test helper
        # behind a future that simply never resolves.
        future.set_result(fn(*args, **kwargs))
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        pass


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


def create_guard(
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    probe: SolveProbe | None = None,
    poll_probe: SolveProbe | None = None,
    pool: PoolResolution | None = None,
    key_file: Path | None = None,
    write_ledger: bool = True,
    wait_turn: bool = True,
    now: datetime = NOW,
    seeded: bool = False,
) -> tuple[LeetcodeGuard, dict[str, Any]]:
    """Build a guard plus a record of what its fake network was asked.

    Args:
        tmp_path: Per-test directory for the ledger and escape history.
        demo_mode: Which lock configuration to arm with.
        probe: The startup probe, used for seeding.
        poll_probe: What each subsequent poll returns. Defaults to ``probe``.
        pool: The suggestion list.
        key_file: HMAC key. ``None`` means integrity checking is off.
        write_ledger: Whether the guard may persist anything.
        now: Fixed clock.
        seeded: Pre-seed the ledger on an earlier day, so the guard starts on
            an ordinary gating day. Seeding settles the day it runs on, so a
            guard that seeds itself is by definition unlocked -- any test about
            locked behaviour wants this. The seed lands on the preceding
            *Friday* rather than the day before, because ``NOW`` is a Monday and
            a Sunday seed would settle a weekend day at double cost, making
            every balance in every test two off for no reason anyone reading it
            would guess.

    Returns:
        The guard and a dict recording every network call.
    """
    startup = probe if probe is not None else probe_of()
    if seeded:
        seed_ledger(
            Ledger(),
            startup,
            day=now.date() - timedelta(days=3),
            now=now,
            path=tmp_path / "ledger.json",
            key_file=key_file,
        )
    polled = poll_probe if poll_probe is not None else startup
    calls: dict[str, Any] = {"posts": 0}

    def post(_query: str, _variables: dict[str, Any]) -> Any:
        calls["posts"] += 1
        return None

    guard = LeetcodeGuard(
        demo_mode=demo_mode,
        deps=GuardDeps(
            ledger_path=tmp_path / "ledger.json",
            escape_path=tmp_path / "escape.json",
            post=post,
            username="kuchy",
            auth=SIGNED_OUT,
            pool=pool if pool is not None else pool_of("two-sum"),
            probe=startup,
            key_file=key_file,
            write_ledger=write_ledger,
            wait_turn=wait_turn,
            executor=InlineExecutor(),
            now=lambda: now,
        ),
    )
    # The poller's work function is the only thing that would really call the
    # network; swap it for the scripted probe so tests drive the loop by hand.
    guard._check = lambda: polled
    return guard, calls
