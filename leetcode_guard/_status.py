"""Read-only view of the gate's state.

Backs ``--status``, ``python3 -m leetcode_guard._status`` and the MCP
server. Offline by default: the ledger and the pool cache answer every question
here, and neither the status command nor an MCP tool should ever be able to
trigger a network fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from leetcode_guard._auth import load_cookies
from leetcode_guard._clock_guard import check_clock
from leetcode_guard._constants import (
    COOKIES_FILE,
    LEDGER_FILE,
    POOL_CACHE_FILE,
    SUGGESTION_COUNT,
)
from leetcode_guard._daycost import local_today, weekday_name
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._status_format import format_status
from leetcode_guard._status_model import (
    BalanceView,
    PoolView,
    StatusSnapshot,
    Suggestion,
    Verdict,
)
from leetcode_guard._status_unit import gather_unit

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger

_EXIT_OK: Final = 0
_EXIT_LOCKED: Final = 1


@dataclass(frozen=True)
class PoolFiles:
    """Where the suggestion pool is read from; ``None`` is the deployed file.

    The cache and the cookies travel together because they only ever feed one
    call, ``resolve_pool``: the cookies decide whether LeetCode's own
    solved-filter applied to what the cache holds.
    """

    cache: Path | None = None
    cookies: Path | None = None


def gather_status(
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
    key_file: Path | None = None,
    limit: int = SUGGESTION_COUNT,
    pool_files: PoolFiles | None = None,
) -> StatusSnapshot:
    """Assemble the snapshot. Reads only; writes nothing, fetches nothing."""
    moment = now if now is not None else datetime.now().astimezone()
    day = local_today(now=moment)

    path = LEDGER_FILE if ledger_path is None else ledger_path
    ledger = load_ledger(path, key_file=key_file)
    decision = decide_today(ledger, day=day, now=moment, key_file=key_file)

    return StatusSnapshot(
        day=day.isoformat(),
        weekday=weekday_name(day),
        cost=decision.cost,
        debt=decision.debt,
        surcharge=min(decision.debt.surcharge_on(decision.day), decision.cost),
        clock_trusted=check_clock(ledger, day=day).trusted,
        verdict=_verdict(decision),
        balance=_balance_view(decision),
        pool=_pool_view(
            ledger, pool_files or PoolFiles(), now=moment.timestamp(), limit=limit
        ),
        unit=gather_unit(ledger, path, day=day, key_file=key_file),
    )


def _verdict(decision: GateDecision) -> Verdict:
    return Verdict(
        state=decision.state.value,
        locked=decision.locked,
        reason=decision.reason,
        needed=decision.needed,
        charged_today=decision.state.value == "already-charged",
    )


def _balance_view(decision: GateDecision) -> BalanceView:
    balance = decision.balance
    return BalanceView(
        credits=balance.credits,
        charged=balance.charged,
        available=balance.available,
        integrity_ok=balance.integrity_ok,
        tampered=balance.tampered,
        discounted=balance.discounted,
        unparsable=balance.unparsable,
        solves=dict(balance.solves),
    )


def _pool_view(ledger: Ledger, files: PoolFiles, *, now: float, limit: int) -> PoolView:
    auth = load_cookies(COOKIES_FILE if files.cookies is None else files.cookies)
    # `post=None` is what makes this read-only: resolve_pool cannot fetch.
    pool = resolve_pool(
        None,
        POOL_CACHE_FILE if files.cache is None else files.cache,
        now=now,
        solved=SolvedKnowledge(auth=auth, slugs=solved_slugs(ledger)),
    )
    blocks = pool.blocks
    return PoolView(
        auth_present=auth.present,
        auth_note=auth.note,
        source=pool.source,
        notes=pool.notes,
        suggestions=tuple(
            Suggestion(
                title=problem.title,
                difficulty=problem.difficulty,
                ac_rate=problem.ac_rate,
                url=problem.url,
                unit="" if blocks is None else blocks.unit_id(problem),
                theory="" if blocks is None else blocks.theory_of(problem).value,
            )
            for problem in pool.problems[:limit]
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python3 -m leetcode_guard._status``."""
    configure_logging(verbose=bool(argv and "--verbose" in argv))
    snapshot = gather_status()
    print(format_status(snapshot))
    return _EXIT_LOCKED if snapshot.verdict.locked else _EXIT_OK
