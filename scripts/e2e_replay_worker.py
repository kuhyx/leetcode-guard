#!/usr/bin/env python3
"""What the gate decides on each of the last N days, as JSON lines (read-only).

Run by ``e2e_theory g`` once per tree (base and new) with the tree as working
directory and ``PYTHONPATH``, under a scratch ``$HOME`` holding a COPY of the
real state. Pure decision functions only (``load_ledger`` + ``decide_today``
with the day passed in): no network, no window, no write. Per day two
point-in-time views of the same ledger: ``morning`` (rows of earlier days
only: what the lock faced when the day began) and ``evening`` (rows up to and
including the day). Usage: ``e2e_replay_worker.py <tree> <hmac key> [days]``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
import json
from pathlib import Path
import sys

import leetcode_guard
from leetcode_guard import _constants
from leetcode_guard._daycost import local_today
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_io import Ledger, load_ledger


def _view(ledger: Ledger, day: str, *, inclusive: bool) -> Ledger:
    """The ledger as it stood: rows dated before ``day`` (or up to it)."""
    keep = {
        entry_id: entry
        for entry_id, entry in ledger.entries.items()
        if entry.day < day or (inclusive and entry.day == day)
    }
    return replace(ledger, entries=keep)


def main(tree: str, key: Path, days: int) -> int:
    """Print one JSON line per (day, view); exit 2 when run from the wrong tree."""
    here = Path(leetcode_guard.__file__).resolve()
    if not here.is_relative_to(Path(tree).resolve()):
        sys.stderr.write(f"wrong tree: {here}\n")
        return 2
    ledger = load_ledger(_constants.LEDGER_FILE, key_file=key)
    today = local_today(now=datetime.now().astimezone())
    for back in range(days - 1, -1, -1):
        day = today - timedelta(days=back)
        noon = datetime.combine(day, time(12)).astimezone()
        for name, inclusive in (("morning", False), ("evening", True)):
            seen = _view(ledger, day.isoformat(), inclusive=inclusive)
            verdict = decide_today(seen, day=day, now=noon, key_file=key)
            balance = verdict.balance
            row = {
                "day": day.isoformat(),
                "view": name,
                "state": verdict.state.name,
                "locked": verdict.locked,
                "cost": verdict.cost,
                "needed": verdict.needed,
                "credits": balance.credits,
                "charged": balance.charged,
                "available": balance.available,
                "discounted": balance.discounted,
                "tampered": balance.tampered,
                "solves": balance.solves,
                "debt_owed": verdict.debt.owed,
                "debt_repaid": verdict.debt.repaid,
                "debt_missed": verdict.debt.missed_days,
                "reason": verdict.reason,
                "rows": len(seen.entries),
            }
            sys.stdout.write(json.dumps(row, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    tree_arg, key_arg, days_arg = sys.argv[1:4]
    sys.exit(main(tree_arg, Path(key_arg), int(days_arg)))
