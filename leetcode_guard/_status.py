"""Read-only view of the gate's state.

Backs ``--status``, ``python3 -m leetcode_guard._status`` and the MCP
server. Offline by default: the ledger and the pool cache answer every question
here, and neither the status command nor an MCP tool should ever be able to
trigger a network fetch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._auth import load_cookies
from leetcode_guard._clock_guard import check_clock
from leetcode_guard._constants import (
    COOKIES_FILE,
    LEDGER_FILE,
    POOL_CACHE_FILE,
    SUGGESTION_COUNT,
)
from leetcode_guard._daycost import local_today, weekday_name
from leetcode_guard._debt import debt_summary
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._progress import DIFFICULTY_WEIGHTS
from leetcode_guard._status_model import (
    BalanceView,
    PoolView,
    StatusSnapshot,
    Suggestion,
    Verdict,
)

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


def weighting_line(solves: dict[str, int]) -> str | None:
    """``Easy x1: 154, Medium x2: 0, ...`` -- how the credits above were priced."""
    if not any(solves.values()):
        return None
    parts = [
        f"{name} x{weight}: {solves.get(name, 0)}"
        for name, weight in DIFFICULTY_WEIGHTS.items()
    ]
    if solves.get("unknown"):
        parts.append(f"no difficulty yet (counted Easy): {solves['unknown']}")
    return "priced     " + ", ".join(parts)


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

    ledger = load_ledger(
        LEDGER_FILE if ledger_path is None else ledger_path, key_file=key_file
    )
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
            )
            for problem in pool.problems[:limit]
        ),
    )


def snapshot_dict(snapshot: StatusSnapshot) -> dict[str, Any]:
    """The snapshot as plain data, for the MCP server.

    Flat, with the keys and order the MCP tools have always returned: the
    grouping in ``_status_model`` is an internal shape, not a contract change.
    """
    debt, verdict, balance, pool = (
        snapshot.debt,
        snapshot.verdict,
        snapshot.balance,
        snapshot.pool,
    )
    return {
        "day": snapshot.day,
        "weekday": snapshot.weekday,
        "cost": snapshot.cost,
        "debt": asdict(debt),
        "surcharge": snapshot.surcharge,
        "debt_owed": debt.owed,
        "debt_repaid": debt.repaid,
        "debt_outstanding": debt.outstanding,
        "missed_days": debt.missed_days,
        "credits": balance.credits,
        "charged": balance.charged,
        "available": balance.available,
        "needed": verdict.needed,
        "state": verdict.state,
        "locked": verdict.locked,
        "reason": verdict.reason,
        "charged_today": verdict.charged_today,
        "integrity_ok": balance.integrity_ok,
        "tampered": balance.tampered,
        "discounted": balance.discounted,
        "unparsable": balance.unparsable,
        "clock_trusted": snapshot.clock_trusted,
        "auth_present": pool.auth_present,
        "auth_note": pool.auth_note,
        "pool_source": pool.source,
        "pool_notes": pool.notes,
        "suggestions": tuple(asdict(item) for item in pool.suggestions),
        "solves": dict(balance.solves),
    }


def format_status(snapshot: StatusSnapshot) -> str:
    """Render the snapshot for a terminal."""
    costs = f"costs {snapshot.cost}"
    if snapshot.surcharge:
        costs += f" ({snapshot.cost - snapshot.surcharge} +{snapshot.surcharge} debt)"
    balance, verdict = snapshot.balance, snapshot.verdict
    lines = [
        f"day        {snapshot.day} ({snapshot.weekday}), {costs}",
        f"credits    {balance.credits} earned - {balance.charged} spent "
        f"= {balance.available} available",
        f"debt       {debt_summary(snapshot.debt)}",
        f"state      {verdict.state} -- {verdict.reason}",
    ]
    if priced := weighting_line(balance.solves):
        lines.insert(2, priced)
    if verdict.needed:
        plural = "" if verdict.needed == 1 else "s"
        lines.append(f"needed     {verdict.needed} more solve{plural} to unlock today")
    if not balance.integrity_ok:
        lines.append("integrity  OFF -- the HMAC key is unreadable")
    if balance.tampered:
        lines.append(f"tampered   {balance.tampered} entries failed their signature")
    if balance.discounted:
        lines.append(f"refused    {balance.discounted} credits were not counted")
    if balance.unparsable:
        lines.append(f"unreadable {balance.unparsable} ledger rows could not be parsed")
    if not snapshot.clock_trusted:
        lines.append("clock      UNTRUSTED -- the system date moved backwards")
    lines.append(
        f"pool       {len(snapshot.pool.suggestions)} suggestions "
        f"from {snapshot.pool.source}"
    )
    lines.extend(f"  note: {note}" for note in snapshot.pool.notes)
    lines.extend(
        f"  {index:2d}. {item.title} -- {item.difficulty} - {item.ac_rate:.1f}%"
        for index, item in enumerate(snapshot.pool.suggestions, start=1)
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python3 -m leetcode_guard._status``."""
    configure_logging(verbose=bool(argv and "--verbose" in argv))
    snapshot = gather_status()
    print(format_status(snapshot))
    return _EXIT_LOCKED if snapshot.verdict.locked else _EXIT_OK
