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

Suggestions come from the on-disk cache only: ``resolve_pool`` is called with
``post=None``, so an MCP call can never trigger a live fetch and can never
count against the LeetCode rate limit.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Final

from mcp.server.fastmcp import FastMCP

from leetcode_guard._constants import SUGGESTION_COUNT
from leetcode_guard._status import gather_status, snapshot_dict

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

_logger: Final = logging.getLogger(__name__)

mcp: Final = FastMCP("leetcode-guard")


@mcp.tool()
def get_status() -> dict[str, Any]:
    """Everything the gate currently knows.

    Today's cost, the ledger position, the decision and its reason, integrity
    flags, and the cached suggestion list.
    """
    return snapshot_dict(gather_status())


@mcp.tool()
def get_credits() -> dict[str, Any]:
    """Just the credit position, for a status line or a quick check."""
    snapshot = gather_status()
    return {
        "credits": snapshot.credits,
        "charged": snapshot.charged,
        "available": snapshot.available,
        "today_cost": snapshot.cost,
        "needed": snapshot.needed,
        "locked": snapshot.locked,
        "integrity_ok": snapshot.integrity_ok,
    }


@mcp.tool()
def get_suggested_problems(limit: int = SUGGESTION_COUNT) -> list[dict[str, Any]]:
    """Non-premium problems, easiest first then highest acceptance.

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
        }
        for item in snapshot.suggestions
    ]


@mcp.tool()
def explain_lock() -> dict[str, Any]:
    """Why the gate would lock or unlock right now, with the evidence."""
    snapshot = gather_status()
    return {
        "day": snapshot.day,
        "weekday": snapshot.weekday,
        "cost": snapshot.cost,
        "state": snapshot.state,
        "locked": snapshot.locked,
        "reason": snapshot.reason,
        "needed": snapshot.needed,
        "charged_today": snapshot.charged_today,
        "clock_trusted": snapshot.clock_trusted,
        "integrity_ok": snapshot.integrity_ok,
        "tampered": snapshot.tampered,
        "discounted": snapshot.discounted,
        "unparsable": snapshot.unparsable,
        "auth_present": snapshot.auth_present,
        "auth_note": snapshot.auth_note,
        "pool_source": snapshot.pool_source,
        "pool_notes": list(snapshot.pool_notes),
    }


def main() -> None:
    """Serve over stdio."""
    mcp.run()  # pragma: no cover


if __name__ == "__main__":
    main()
