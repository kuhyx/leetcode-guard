"""Read the workday-stick penalty wake-alarm signed for today.

A missed Tuesday/Wednesday/Thursday wake-alarm ring costs tomorrow its
Tue/Wed/Thu price discount (see ``_daycost.Pricing.doubled_days``) instead of
just resetting to normal. This module never re-derives that policy: the file
carries a signed ``penalty_date``, and the only decision here is *HMAC ok,
dated today*. Anything else -- missing file, stale date, bad signature -- is
"no penalty", i.e. today's ordinary price.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from gatelock.log_integrity import verify_entry_hmac

from leetcode_guard._constants import WORKDAY_PENALTY_FILE

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


def _read_verified() -> dict[str, object] | None:
    """The file's entry when it exists, parses and verifies; else None."""
    if not WORKDAY_PENALTY_FILE.exists():
        _logger.debug("No workday penalty file at %s", WORKDAY_PENALTY_FILE)
        return None
    try:
        entry = json.loads(WORKDAY_PENALTY_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Cannot read %s: %s", WORKDAY_PENALTY_FILE, exc)
        return None
    if not isinstance(entry, dict) or not verify_entry_hmac(entry):
        _logger.warning("Workday penalty file is not a signed object")
        return None
    return entry


def workday_penalty_for(day: date) -> bool:
    """Whether ``day`` lost its Tue/Wed/Thu discount to a missed prior ring."""
    entry = _read_verified()
    if entry is None:
        return False
    return entry.get("penalty_date") == day.isoformat()
