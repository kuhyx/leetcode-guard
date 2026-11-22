"""The status snapshot as text (``--status``) and as flat data (MCP).

Split from ``_status`` (which gathers the snapshot) so each stays under the
250-line cap. Pure functions of a :class:`StatusSnapshot`: nothing here reads
a file or the clock.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from leetcode_guard._debt import debt_summary
from leetcode_guard._progress import DIFFICULTY_WEIGHTS
from leetcode_guard._status_unit import unit_lines

if TYPE_CHECKING:
    from leetcode_guard._status_model import StatusSnapshot


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
    lines.extend(unit_lines(snapshot.unit))
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
