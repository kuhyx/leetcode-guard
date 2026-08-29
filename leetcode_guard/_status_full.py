"""Everything the project knows, gathered into one object.

:mod:`leetcode_guard._status` answers the gate's question. This adds the rest
of it -- solve history, budgets, cache freshness, whether systemd will even
fire -- because the whole point of the status window is that you should never
have to go and read a JSON file to find out what happened.

Offline and read-only throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import (
    COOKIES_FILE,
    ESCAPE_HISTORY_FILE,
    GATE_START_DATE,
    LEDGER_FILE,
    NETWORK_INCIDENTS_FILE,
    POOL_CACHE_FILE,
    STATEMENTS_CACHE_FILE,
    SYNC_TOKEN_FILE,
)
from leetcode_guard._daycost import local_today
from leetcode_guard._escape_flow import build_tracker as build_escape_tracker
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._network_incident import build_tracker as build_incident_tracker
from leetcode_guard._status import StatusSnapshot, gather_status
from leetcode_guard._status_extra import (
    BudgetStatus,
    CacheStatus,
    LedgerStats,
    gather_budget,
    gather_cache,
    gather_ledger_stats,
)
from leetcode_guard._status_timer import (
    TimerStatus,
    gather_timer,
)

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

_UNUSED: Final = "-"


@dataclass(frozen=True)
class FullStatus:
    """The gate decision plus every other readable fact."""

    gate: StatusSnapshot
    ledger: LedgerStats
    escape: BudgetStatus
    incidents: BudgetStatus
    pool_cache: CacheStatus
    statement_cache: CacheStatus
    timer: TimerStatus
    start_date: str
    in_force: bool
    sync_configured: bool
    cookies_configured: bool
    ledger_path: str


def gather_full(
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
    key_file: Path | None = None,
) -> FullStatus:
    """Read everything. Touches no network and writes nothing."""
    moment = now if now is not None else datetime.now().astimezone()
    today: date = local_today(now=moment)
    ledger_file = LEDGER_FILE if ledger_path is None else ledger_path

    gate = gather_status(now=moment, ledger_path=ledger_file, key_file=key_file)
    ledger = load_ledger(ledger_file, key_file=key_file)
    seconds = moment.timestamp()

    return FullStatus(
        gate=gate,
        ledger=gather_ledger_stats(ledger, today=today),
        escape=gather_budget(
            build_escape_tracker(ESCAPE_HISTORY_FILE, key_file=key_file), "Escape hatch"
        ),
        incidents=gather_budget(
            build_incident_tracker(NETWORK_INCIDENTS_FILE, key_file=key_file),
            "Network incidents",
        ),
        pool_cache=gather_cache(
            POOL_CACHE_FILE, "Problem pool", "problems", now=seconds
        ),
        statement_cache=gather_cache(
            STATEMENTS_CACHE_FILE, "Offline statements", "statements", now=seconds
        ),
        timer=gather_timer(),
        start_date=str(GATE_START_DATE),
        in_force=today >= GATE_START_DATE,
        sync_configured=SYNC_TOKEN_FILE.exists(),
        cookies_configured=COOKIES_FILE.exists(),
        ledger_path=str(ledger_file),
    )


def explain_not_triggered(full: FullStatus) -> list[str]:
    """Why the gate is in the state it is, in the order the checks run.

    This is the question the window exists to answer. "Unlocked" alone is
    useless when there are five different reasons for it -- you banked credit,
    the gate is not in force yet, the timer is not even enabled -- and they all
    look identical from the outside.

    The integrity and clock warnings are appended in **every** case, locked
    included. An earlier version returned early on a locked gate, which hid the
    "N credits were refused" line at precisely the moment it explained the
    lock.
    """
    gate = full.gate
    lines: list[str] = []

    if not full.timer.enabled:
        lines.append(
            f"The systemd timer is NOT enabled ({full.timer.detail}), so the gate "
            "would not have fired at all today."
        )
    if not full.in_force:
        # The gate's own reason says the same thing, so it is not repeated
        # below -- a duplicated explanation reads like two separate causes.
        lines.append(
            f"The gate is not in force until {full.start_date}; every scheduled "
            "run exits immediately until then."
        )

    if gate.locked:
        lines.append(f"It WOULD lock right now: {gate.reason}")
    elif gate.state == "already-charged":
        lines.append(
            "Today was already settled by an earlier run, so a second run is a "
            "no-op. That is what makes the afternoon retry free."
        )
    elif gate.state == "charged":
        lines.append(
            f"You had {gate.credits - gate.charged + gate.cost} credit(s) banked "
            f"and {gate.weekday} costs {gate.cost}, so the day was paid for "
            "without asking you to solve anything."
        )
    elif gate.state == "not-started" and full.in_force:
        lines.append(gate.reason)

    lines.extend(_warnings(gate))
    return lines


def _warnings(gate: StatusSnapshot) -> list[str]:
    """Anything wrong with the ledger itself, regardless of the verdict."""
    lines: list[str] = []
    if gate.discounted:
        lines.append(
            f"{gate.discounted} credit(s) in the ledger were REFUSED (bad "
            "signature, or written by another device) -- which may be why the "
            "balance is lower than you expect."
        )
    if gate.tampered:
        lines.append(f"{gate.tampered} ledger entries failed their signature check.")
    if gate.unparsable:
        lines.append(f"{gate.unparsable} ledger rows could not be read at all.")
    if not gate.integrity_ok:
        lines.append("Ledger integrity checking is OFF -- the HMAC key is unreadable.")
    if not gate.clock_trusted:
        lines.append("The system clock has moved backwards past a settled day.")
    return lines
