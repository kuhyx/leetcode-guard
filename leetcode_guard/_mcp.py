"""Read-only MCP server exposing the gate's state.

Three invariants. Do not break them when adding a tool.

**1. READ-ONLY.** There is deliberately no ``grant_credit``, no ``mark_solved``
and no ``unlock``. A credit exists only because LeetCode confirmed an accepted
submission -- never because a caller said so. An agent that could mint a credit
would make the whole gate decorative, and it would do so silently. Every tool
below calls only side-effect-free leaf helpers.

**2. stdout is the JSON-RPC channel.** Logging goes to stderr and nothing here
may ``print``. No tool may call :mod:`leetcode_guard._cli`, which prints, opens
windows and calls ``sys.exit``.

**3. No secret ever leaves.** Nothing returns the sync token, the cookie file
or any HMAC key.

The current unit and phase (stage 4) come from ``_status_unit``, the same
read-only view the lock paints: it never polls the tutor ledger for credit,
never mints and never writes ``theory_phase.json``.

Suggestions come from the on-disk cache only: ``resolve_pool`` is called with
``post=None``, so an MCP call can never trigger a live fetch and can never
count against the LeetCode rate limit.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Final

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from leetcode_guard import _attempt_report, _coach_reviews, _status_unit
from leetcode_guard._constants import SUGGESTION_COUNT
from leetcode_guard._status import gather_status, snapshot_dict

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

_logger: Final = logging.getLogger(__name__)

mcp: Final = MCPServer("leetcode-guard")

# Every tool here only reads local state: the ledger, the cached problem pool
# and the clock. Saying so lets a client run them without asking -- and the
# day one of them stops being read-only, this annotation is the thing that has
# to change with it.
_READS_ONLY: Final = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)


@mcp.tool(title="LeetCode gate status", annotations=_READS_ONLY)
def get_status() -> dict[str, Any]:
    """Everything the gate currently knows.

    Today's cost, the ledger position, the decision and its reason, integrity
    flags, the cached suggestion list, and ``unit``: the current unit, its
    phase (``theory``/``solve``/``none``), what the lock leads with and why.
    ``null`` means "could not check", never zero.
    """
    snapshot = gather_status()
    return {**snapshot_dict(snapshot), "unit": _unit(snapshot.unit)}


def _unit(unit: _status_unit.UnitStatus) -> dict[str, Any]:
    return {
        **_status_unit.unit_dict(unit),
        "lead_reason": _status_unit.lead_reason(unit),
    }


@mcp.tool(title="Solve credits and cost", annotations=_READS_ONLY)
def get_credits() -> dict[str, Any]:
    """Just the credit position, for a status line or a quick check.

    ``theory_credits`` (all time) and ``theory_credits_today`` are the ledger's
    trusted ``tutor-theory`` credits (``entry_id`` ``theory:<day>:<n>``, 12
    taught minutes each); ``solve_credits`` is the rest of ``credits``.
    """
    snapshot = gather_status()
    unit = snapshot.unit
    return {
        "credits": snapshot.balance.credits,
        "charged": snapshot.balance.charged,
        "available": snapshot.balance.available,
        "today_cost": snapshot.cost,
        "surcharge": snapshot.surcharge,
        "debt_outstanding": snapshot.debt.outstanding,
        "missed_days": snapshot.debt.missed_days,
        "needed": snapshot.verdict.needed,
        "locked": snapshot.verdict.locked,
        "integrity_ok": snapshot.balance.integrity_ok,
        "theory_credits": unit.credits_total,
        "theory_credits_today": unit.credits_today,
        "solve_credits": snapshot.balance.credits - unit.credits_total,
    }


@mcp.tool(title="Suggested problems", annotations=_READS_ONLY)
def get_suggested_problems(limit: int = SUGGESTION_COUNT) -> list[dict[str, Any]]:
    """Non-premium problems in the order the lock ranks them.

    In THEORY(u) and SOLVE(u) the current unit u's Easy problems lead
    (``_unit_rank.focus_key``); in ``none`` the curriculum order. ``unit``
    names each row's block; ``theory`` says whether the tutor has taught it.
    The lock checks its top rows live; this list is the cache's order.

    Served from the cached pool. This never fetches, so it is always instant
    and never contributes to rate limiting.
    """
    snapshot = gather_status(limit=limit)
    return [
        {
            "title": item.title,
            "difficulty": item.difficulty,
            "ac_rate": item.ac_rate,
            "url": item.url,
            "unit": item.unit,
            "theory": item.theory,
        }
        for item in snapshot.pool.suggestions
    ]


@mcp.tool(title="Why the gate is locked", annotations=_READS_ONLY)
def explain_lock() -> dict[str, Any]:
    """Why the gate would lock or unlock right now, with the evidence.

    Also the current unit and phase, and ``leads_with``/``lead_reason``: why the
    lock leads with theory or with problems.
    """
    snapshot = gather_status()
    return {
        **_unit(snapshot.unit),
        "day": snapshot.day,
        "weekday": snapshot.weekday,
        "cost": snapshot.cost,
        "state": snapshot.verdict.state,
        "locked": snapshot.verdict.locked,
        "reason": snapshot.verdict.reason,
        "needed": snapshot.verdict.needed,
        "charged_today": snapshot.verdict.charged_today,
        "clock_trusted": snapshot.clock_trusted,
        "integrity_ok": snapshot.balance.integrity_ok,
        "tampered": snapshot.balance.tampered,
        "discounted": snapshot.balance.discounted,
        "unparsable": snapshot.balance.unparsable,
        "auth_present": snapshot.pool.auth_present,
        "auth_note": snapshot.pool.auth_note,
        "pool_source": snapshot.pool.source,
        "pool_notes": list(snapshot.pool.notes),
    }


@mcp.tool(title="Slow solves to review", annotations=_READS_ONLY)
def get_flagged() -> dict[str, Any]:
    """Solves that took over 20 min of active time though the theory was taught.

    Also the last 28 days' measured and unknown solves and the share under
    10 min (``null`` with no data). A solve the coach has reviewed is not
    flagged. Display-only: it reads ``attempts.json``, the ledger and the
    coach log, and writes nothing.
    """
    return _attempt_report.load_report(cleared=_coach_reviews.reviewed_slugs())


def main() -> None:
    """Serve over stdio."""
    mcp.run()  # pragma: no cover


if __name__ == "__main__":
    main()
