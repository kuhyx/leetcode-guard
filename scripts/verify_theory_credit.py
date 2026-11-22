#!/usr/bin/env python3
"""Check that real theory minutes minted a credit, paid the same on both sides.

Read-only. Run it after a real lesson on the current unit::

    python3 -m scripts.verify_theory_credit [YYYY-MM-DD]

Three checks for the day (default today), each printed as ``ok``/``FAIL``:

1. the guard ledger holds a signed ``theory:<day>:<n>`` row with
   ``detail.source`` ``tutor-theory``, written within ``LAG_S`` of the moment
   the tutor rows of its unit reached ``n * 12`` minutes;
2. the day has signed tutor teaching rows carrying a string
   ``detail.subject`` and ``detail.module`` (C1), and no row carries only one;
3. ``earned_time`` pays the tutor exactly what its quota rule makes of the sum
   of ``detail.minutes`` over the day's verified rows.

Exit 0 only when all three hold; exit 1 otherwise, including the day nobody
taught (no theory row yet is a failure here, not a skip).
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Final

import earned_time
from gatelock.log_integrity import DEFAULT_HMAC_KEY_FILE, verify_entry_hmac

from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._ledger import verify
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._theory_credit import MINUTES_PER_CREDIT, SOURCE_THEORY
from leetcode_guard._tutor_read import read_tutor_json
from leetcode_guard._tutor_signed import TUTOR_DIR

if TYPE_CHECKING:
    from leetcode_guard._ledger import LedgerEntry

LAG_S: Final = 60.0
_logger: Final = logging.getLogger(__name__)
# The e2e harness's scratch key (``E2E_KEY``); the real one otherwise.
KEY_FILE: Final = Path(os.environ.get("E2E_KEY") or DEFAULT_HMAC_KEY_FILE)
_EXIT_OK: Final = 0
_EXIT_FAIL: Final = 1

Row = dict[str, object]


def _say(*, ok: bool, what: str) -> bool:
    """Print one verdict line; return ``ok``."""
    sys.stdout.write(f"{'ok  ' if ok else 'FAIL'} {what}\n")
    return ok


def _tutor_rows(day: date) -> list[Row]:
    """The tutor's verified credit rows whose ``ended_at`` falls on ``day``."""
    document = read_tutor_json(TUTOR_DIR / "ledger.json", _logger)
    rows = document.get("entries") if isinstance(document, dict) else None
    out: list[Row] = []
    for row in rows if isinstance(rows, list) else []:
        detail = row.get("detail") if isinstance(row, dict) else None
        ended = detail.get("ended_at") if isinstance(detail, dict) else None
        if not isinstance(ended, (int, float)) or isinstance(ended, bool):
            continue
        if datetime.fromtimestamp(ended).astimezone().date() != day:
            continue
        if verify_entry_hmac(row, key_file=KEY_FILE):
            out.append(row)
    return out


def _detail(row: Row) -> dict[str, object]:
    """The row's ``detail`` (callers already know it is a dict)."""
    detail = row.get("detail")
    return detail if isinstance(detail, dict) else {}


def _minutes(row: Row) -> int:
    """``detail.minutes`` as an int, 0 when missing."""
    raw = _detail(row).get("minutes")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


def _reached_at(rows: list[Row], unit: str, target: int) -> float | None:
    """When the unit's modules reached ``target`` minutes, by ``ended_at``."""
    curriculum = load_curriculum()
    found = [u for u in curriculum.units if u.unit_id == unit] if curriculum else []
    if not found:
        return None
    subject, modules = found[0].subject, set(found[0].modules)
    total = 0
    on_unit = [
        r
        for r in rows
        if _detail(r).get("subject") == subject and _detail(r).get("module") in modules
    ]
    for row in sorted(on_unit, key=lambda r: float(str(_detail(r)["ended_at"]))):
        total += _minutes(row)
        if total >= target:
            return float(str(_detail(row)["ended_at"]))
    return None


def check_theory_rows(day: date, rows: list[Row]) -> bool:
    """Check 1: a signed theory row, minted within ``LAG_S`` of its minute."""
    ledger = load_ledger(LEDGER_FILE, key_file=KEY_FILE)
    prefix = f"theory:{day.isoformat()}:"
    minted: list[LedgerEntry] = [
        e
        for e in ledger.entries.values()
        if e.entry_id.startswith(prefix) and e.detail.get("source") == SOURCE_THEORY
    ]
    if not minted:
        return _say(ok=False, what=f"no {prefix}<n> row with source {SOURCE_THEORY}")
    ok = True
    for entry in minted:
        n = int(entry.entry_id.rsplit(":", 1)[1])
        unit = str(entry.detail.get("unit"))
        reached = _reached_at(rows, unit, n * MINUTES_PER_CREDIT)
        written = datetime.fromisoformat(entry.created_at).timestamp()
        lag = None if reached is None else written - reached
        signed = verify(entry, key_file=KEY_FILE)
        good = signed and lag is not None and 0 <= lag <= LAG_S
        what = f"{entry.entry_id} signed={signed} lag_s={lag} (max {LAG_S:.0f})"
        ok = _say(ok=good, what=what) and ok
    return ok


def check_tutor_rows(rows: list[Row]) -> bool:
    """Check 2: signed teaching rows carry both keys; no row carries one alone.

    Only a teaching turn carries them (tutor ``DOCS-contract.md`` §7, C1);
    review, drill, carry and leftover rows carry neither, so they are not
    counted against it.
    """
    keys = ("subject", "module")
    tagged = [r for r in rows if all(isinstance(_detail(r).get(k), str) for k in keys)]
    half = [
        r.get("entry_id")
        for r in rows
        if r not in tagged and any(k in _detail(r) for k in keys)
    ]
    return _say(
        ok=bool(tagged) and not half,
        what=f"{len(tagged)} of {len(rows)} signed tutor rows carry subject+module"
        f"; with only one or a non-string: {half}",
    )


def check_units(day: date, rows: list[Row]) -> bool:
    """Check 3: earned_time's units equal its quota rule over the minutes."""
    tutor = earned_time.TUTOR
    minutes = sum(_minutes(r) for r in rows)
    quota = earned_time.tutor_quota_for(day)
    most = tutor.max_units or quota or minutes
    expected = minutes if quota is None else tutor.capped(minutes * most // quota)
    paid = earned_time.credit_units(tutor, TUTOR_DIR / "ledger.json", KEY_FILE, day)
    return _say(
        ok=paid == expected,
        what=f"earned_time units={paid}, from {minutes} minutes expected {expected}",
    )


def main(argv: list[str]) -> int:
    """Run the three checks for the day in ``argv`` (default today)."""
    day = date.fromisoformat(argv[0]) if argv else datetime.now().astimezone().date()
    rows = _tutor_rows(day)
    results = [
        check_theory_rows(day, rows),
        check_tutor_rows(rows),
        check_units(day, rows),
    ]
    return _EXIT_OK if all(results) else _EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
