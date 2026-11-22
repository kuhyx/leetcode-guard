#!/usr/bin/env python3
"""Check that real theory minutes minted a credit, paid the same on both sides.

Read-only. Run it after a real lesson on the current unit::

    python3 -m scripts.verify_theory_credit [YYYY-MM-DD]

Three checks for the day (default today), each printed as ``ok``/``FAIL``:

1. the guard ledger holds a signed ``theory:<day>:<n>`` row with
   ``detail.source`` ``tutor-theory``, written within ``LAG_S`` of the moment
   the day's pool reached ``n * 12`` minutes (the unit's lesson rows plus every
   tagged review row, plus what other units' credits spent of those reviews);
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
from leetcode_guard._theory_credit import SOURCE_THEORY
from leetcode_guard._theory_pool import spent_elsewhere
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
    """When the unit's lessons plus every mapped review reached ``target`` minutes.

    A review row is a tagged one (``activity == "review"``) on any mapped card;
    the ``review`` label (phase ``none``) has no lessons, only reviews.
    """
    curriculum = load_curriculum()
    if curriculum is None:
        return None
    found = [u for u in curriculum.units if u.unit_id == unit]
    subject, modules = (
        (found[0].subject, set(found[0].modules)) if found else ("", set())
    )
    mapped = {(u.subject, m) for u in curriculum.units for m in u.modules}
    total = 0
    on_unit = [r for r in rows if _counts(r, (subject, modules), mapped)]
    for row in sorted(on_unit, key=lambda r: float(str(_detail(r)["ended_at"]))):
        total += _minutes(row)
        if total >= target:
            return float(str(_detail(row)["ended_at"]))
    return None


def _counts(
    row: Row, lessons: tuple[str, set[str]], mapped: set[tuple[str, str]]
) -> bool:
    """Whether the row is a lesson on the unit or a tagged review on a mapped card."""
    detail = _detail(row)
    pair = (detail.get("subject"), detail.get("module"))
    if detail.get("activity") == "review":
        return pair in mapped
    return pair[0] == lessons[0] and pair[1] in lessons[1]


def _lag(
    entry: LedgerEntry,
    minted: list[LedgerEntry],
    rows: list[Row],
    *,
    integrity_ok: bool,
) -> float | None:
    """Seconds from the pool reaching a credit's cut to its write; None = never."""
    unit = str(entry.detail.get("unit"))
    cut = int(entry.detail.get("minutes", "0"))  # 12*k for the unit's k-th credit
    spent = spent_elsewhere(minted, unit, integrity_ok=integrity_ok)
    reached = _reached_at(rows, unit, cut + spent)
    written = datetime.fromisoformat(entry.created_at).timestamp()
    return None if reached is None else written - reached


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
        lag = _lag(entry, minted, rows, integrity_ok=ledger.integrity_ok)
        signed = verify(entry, key_file=KEY_FILE)
        good = signed and lag is not None and 0 <= lag <= LAG_S
        what = f"{entry.entry_id} signed={signed} lag_s={lag} (max {LAG_S:.0f})"
        ok = _say(ok=good, what=what) and ok
    return ok


def check_tutor_rows(rows: list[Row]) -> bool:
    """Check 2: signed teaching rows carry both keys; no row carries one alone.

    A teaching turn carries them (tutor ``DOCS-contract.md`` §7, C1), and so
    does a review-minute row (plus ``activity``); drill, carry, leftover and
    the old untagged review rows carry neither, so they are not counted
    against it.
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
