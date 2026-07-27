"""Read-only view of the gate's state.

Backs ``--status``, the ``leetcode-guard-status`` console script and the MCP
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
from leetcode_guard._daycost import day_cost, local_today, weekday_name
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._pool_resolve import resolve_pool

if TYPE_CHECKING:
    from pathlib import Path

_EXIT_OK: Final = 0
_EXIT_LOCKED: Final = 1


@dataclass(frozen=True)
class Suggestion:
    """One suggested problem, flattened for display and for MCP."""

    title: str
    difficulty: str
    ac_rate: float
    url: str


@dataclass(frozen=True)
class StatusSnapshot:
    """Everything the gate knows, without touching the network."""

    day: str
    weekday: str
    cost: int
    credits: int
    charged: int
    available: int
    needed: int
    state: str
    locked: bool
    reason: str
    charged_today: bool
    integrity_ok: bool
    tampered: int
    discounted: int
    unparsable: int
    clock_trusted: bool
    auth_present: bool
    auth_note: str
    pool_source: str
    pool_notes: tuple[str, ...]
    suggestions: tuple[Suggestion, ...]


def gather_status(
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
    cache_path: Path | None = None,
    cookies_path: Path | None = None,
    key_file: Path | None = None,
    limit: int = SUGGESTION_COUNT,
) -> StatusSnapshot:
    """Assemble the snapshot. Reads only; writes nothing, fetches nothing."""
    ledger_file = LEDGER_FILE if ledger_path is None else ledger_path
    pool_file = POOL_CACHE_FILE if cache_path is None else cache_path
    cookie_file = COOKIES_FILE if cookies_path is None else cookies_path

    moment = now if now is not None else datetime.now().astimezone()
    day = local_today(now=moment)

    ledger = load_ledger(ledger_file, key_file=key_file)
    decision = decide(ledger, day=day, now=moment, key_file=key_file)
    clock = check_clock(ledger, day=day)

    auth = load_cookies(cookie_file)
    # `post=None` is what makes this read-only: resolve_pool cannot fetch.
    pool = resolve_pool(None, pool_file, now=moment.timestamp(), auth=auth)

    return StatusSnapshot(
        day=day.isoformat(),
        weekday=weekday_name(day),
        cost=day_cost(day),
        credits=decision.balance.credits,
        charged=decision.balance.charged,
        available=decision.balance.available,
        needed=decision.needed,
        state=decision.state.value,
        locked=decision.locked,
        reason=decision.reason,
        charged_today=decision.state.value == "already-charged",
        integrity_ok=decision.balance.integrity_ok,
        tampered=decision.balance.tampered,
        discounted=decision.balance.discounted,
        unparsable=decision.balance.unparsable,
        clock_trusted=clock.trusted,
        auth_present=auth.present,
        auth_note=auth.note,
        pool_source=pool.source,
        pool_notes=pool.notes,
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
    """The snapshot as plain data, for the MCP server."""
    return asdict(snapshot)


def format_status(snapshot: StatusSnapshot) -> str:
    """Render the snapshot for a terminal."""
    lines = [
        f"day        {snapshot.day} ({snapshot.weekday}), costs {snapshot.cost}",
        f"credits    {snapshot.credits} earned - {snapshot.charged} spent "
        f"= {snapshot.available} available",
        f"state      {snapshot.state} -- {snapshot.reason}",
    ]
    if snapshot.needed:
        plural = "" if snapshot.needed == 1 else "s"
        lines.append(f"needed     {snapshot.needed} more solve{plural} to unlock today")
    if not snapshot.integrity_ok:
        lines.append("integrity  OFF -- the HMAC key is unreadable")
    if snapshot.tampered:
        lines.append(f"tampered   {snapshot.tampered} entries failed their signature")
    if snapshot.discounted:
        lines.append(f"refused    {snapshot.discounted} credits were not counted")
    if snapshot.unparsable:
        lines.append(
            f"unreadable {snapshot.unparsable} ledger rows could not be parsed"
        )
    if not snapshot.clock_trusted:
        lines.append("clock      UNTRUSTED -- the system date moved backwards")
    lines.append(
        f"pool       {len(snapshot.suggestions)} suggestions "
        f"from {snapshot.pool_source}"
    )
    lines.extend(f"  note: {note}" for note in snapshot.pool_notes)
    lines.extend(
        f"  {index:2d}. {item.title} -- {item.difficulty} - {item.ac_rate:.1f}%"
        for index, item in enumerate(snapshot.suggestions, start=1)
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``leetcode-guard-status`` console script."""
    configure_logging(verbose=bool(argv and "--verbose" in argv))
    snapshot = gather_status()
    print(format_status(snapshot))
    return _EXIT_LOCKED if snapshot.locked else _EXIT_OK
