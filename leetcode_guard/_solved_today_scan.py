"""The ledger scan behind :func:`leetcode_guard.solved_today.solved_today`.

Split out of that module for size only; the rules are its docstring's. Rows
arrive raw from the ledger file, so every one is verified here before it can
count -- a forged row is counted as forged and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import logging
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import verify_entry_hmac

from leetcode_guard._daycost import local_today, parse_day
from leetcode_guard._ledger import CHARGE, CREDIT, SOURCE_LEETCODE

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class TodayTally:
    """What today's verified rows say.

    Attributes:
        count: Credits whose accepted submission landed today.
        forged: Credit or charge rows whose signature failed.
        settled: Whether today's charge was paid from verified credits.
    """

    count: int
    forged: int
    settled: bool


def scan_today(rows: list[object], *, moment: datetime, key_file: Path) -> TodayTally:
    """Count today's verified credits and spot a credit-paid charge.

    Args:
        rows: The ledger's raw entry list.
        moment: The current local time.
        key_file: The shared HMAC key every row must verify against.

    Returns:
        The tally; forged rows are counted, never credited.
    """
    midnight = datetime.combine(local_today(now=moment), time.min, moment.tzinfo)
    window = (midnight.timestamp(), moment.timestamp())
    today_key = local_today(now=moment).isoformat()

    count = 0
    forged = 0
    settled = False
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") not in {CREDIT, CHARGE}:
            continue
        if not verify_entry_hmac(row, key_file=key_file):
            forged += 1
            continue
        if row["kind"] == CHARGE:
            detail = row.get("detail")
            settled = settled or (
                row.get("day") == today_key
                and isinstance(detail, dict)
                and detail.get("source") == SOURCE_LEETCODE
            )
        elif _landed_today(row, window=window, today_key=today_key):
            count += 1
    return TodayTally(count=count, forged=forged, settled=settled)


def _landed_today(
    entry: dict[str, object],
    *,
    window: tuple[float, float],
    today_key: str,
) -> bool:
    """Whether this credit's accepted submission happened today, locally.

    Args:
        entry: One ledger entry, already known to be a verified credit.
        window: Local midnight and now, as unix seconds.
        today_key: Today's local ``YYYY-MM-DD``, used only by the fallback.

    Returns:
        Whether the solve falls inside today.
    """
    detail = entry.get("detail")
    raw = detail.get("submitted_at") if isinstance(detail, dict) else None
    if raw is not None:
        try:
            stamp = float(str(raw))
        except ValueError:
            _logger.warning(
                "Credit %r has an unparsable submitted_at (%r) -- falling back "
                "to its day key",
                entry.get("entry_id"),
                raw,
            )
        else:
            start, end = window
            return start <= stamp <= end

    # No usable submission time: fall back to the harvest day. That key is
    # skewed late but never early, so it can miss a late-night solve and can
    # never invent one.
    day = entry.get("day")
    return isinstance(day, str) and day == today_key and parse_day(day) is not None
