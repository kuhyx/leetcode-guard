"""``--repair-review-clear``: mint the missed 2026-11-24 review clear, once.

Hard-wired to the day and unit kuhy reported; ``_review_clear_repair`` holds
the evidence rule. Prints one line; a refusal exits non-zero and writes nothing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import EXIT_LOCKED, EXIT_OK, LEDGER_FILE
from leetcode_guard._ledger_io import load_ledger, save_ledger
from leetcode_guard._review_clear import clear_id
from leetcode_guard._review_clear_repair import Repair, repair_review_clear

if TYPE_CHECKING:
    from pathlib import Path

REPAIR: Final = (date(2026, 11, 24), "prefix-sums")
"""The reported day and the unit that was current then (``curriculum.json``)."""
KEY_FILE: Path | None = None
"""The signing key; ``None`` = the machine's own (tests point it elsewhere)."""


def now_local() -> datetime:
    """The local time, for the row's ``created_at``."""
    return datetime.now().astimezone()


def cmd_repair_review_clear() -> int:
    """Run the repair against the live ledger and say what happened."""
    day, unit = REPAIR
    ledger = load_ledger(LEDGER_FILE, key_file=KEY_FILE)
    result = repair_review_clear(
        ledger, day=day, unit=unit, now=now_local(), key_file=KEY_FILE
    )
    if result is Repair.MINTED:
        save_ledger(LEDGER_FILE, ledger)
    print(f"{result.value} {clear_id(day, unit)}")
    return EXIT_LOCKED if result is Repair.REFUSED else EXIT_OK
