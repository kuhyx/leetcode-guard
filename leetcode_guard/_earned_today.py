"""Credits earned today, for the study strip's filled dots. Display only.

The strip draws one filled dot per credit already earned today, beside one
hollow dot per credit still owed. Both are in the same unit: a credit's value
is what :func:`leetcode_guard._balance.credit_value` gives it (an accepted
solve is its difficulty weight, a theory-minute or finished-module credit is 1).

Derived at read time from the ledger the lock already holds and by the
balance's own rule (:func:`~leetcode_guard._balance.counts_toward_balance`), so
a forged or foreign row never fills a dot. Nothing is stored. **Nothing that
decides, charges or credits may import this**: the strip would turn from a
picture of the day into an input to it. ``test_display_only_imports.py`` bans
it from every decider, transitively.

"Cannot read" is ``None`` (the strip draws no filled dot), never ``0``.
"""

from __future__ import annotations

from collections import defaultdict
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import counts_toward_balance, credit_value
from leetcode_guard._daycost import day_key, local_today
from leetcode_guard._difficulty import load_weights
from leetcode_guard._ledger import CREDIT

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._difficulty import WeightTable
    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


def earned_today(ledger: Ledger, *, day: date, weights: WeightTable | None) -> int:
    """Counted credits whose row is dated ``day``, in the balance's unit.

    By the row's ``day``, not its id: a finish credit (``theory-done:...``) has
    no day in its id and is still one of today's.
    """
    today = day_key(day)
    tally: defaultdict[str, int] = defaultdict(int)  # difficulty mix: unused
    return sum(
        credit_value(entry, weights, tally)
        for entry in ledger.entries.values()
        if entry.kind == CREDIT
        and entry.day == today
        and counts_toward_balance(entry, integrity_ok=ledger.integrity_ok)
    )


def earned_for_strip(
    ledger: Ledger, *, now: datetime, key_file: Path | None
) -> int | None:
    """:func:`earned_today` for the local day of ``now``; ``None`` = cannot read.

    Never raises (``Exception`` only): a bug here costs the filled dots, never
    the strip, and so never the lock.
    """
    try:
        return earned_today(
            ledger,
            day=local_today(now=now),
            weights=load_weights(key_file=key_file),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "earned-today count failed: %s", type(exc).__name__, exc_info=True
        )
        return None
