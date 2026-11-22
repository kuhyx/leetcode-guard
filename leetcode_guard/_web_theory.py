"""``GET /api/theory``: LeetCode's theory accounting, for the tutor's lesson bar.

The tutor server fetches this over loopback and only displays it; the guard
owns every number. Read-only: it never writes a file, mints a credit, seeds
the ledger or takes the instance lock (the route sits beside ``/api/status``,
which cannot either).

Built from SIGNED inputs only: the guard ledger, today's gate decision, the
tutor's signed ``ledger.json``/``module_state.json`` and the phase machine.
``_theory`` (the tutor's unsigned files) is not imported, directly or
transitively; ``test_display_only_imports.py`` checks the closure. That is
why this does not use ``_status_unit``, whose view reads the cards bar.

"Cannot check" is ``None`` (JSON ``null``), never 0. ``checked`` is true only
when no field is ``None``. ``unit`` is ``""`` and ``phase`` ``"none"`` once
every unit is finished (the phase machine's own words); ``minutes_per_credit``
is a constant and always present. A bug inside answers every checkable field
as ``None`` and logs at warning: the route fails open to null.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard import _constants
from leetcode_guard._daycost import day_key, local_today
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._phase_inputs import gather_phase
from leetcode_guard._theory_credit import (
    MINUTES_PER_CREDIT,
    minutes_into_credit,
    theory_credits,
)
from leetcode_guard._theory_pool import paying_minutes

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


def build_theory_payload(
    *, now: datetime | None = None, key_file: Path | None = None
) -> dict[str, Any]:
    """The ``{"theory": {...}}`` payload. Never raises (``Exception`` only).

    Args:
        now: The moment to answer for; ``None`` = the local clock.
        key_file: The HMAC key; ``None`` = the shared key.
    """
    moment = now if now is not None else datetime.now().astimezone()
    day = local_today(now=moment)
    try:
        block = _block(moment, day, key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "theory route failed, answering null: %s",
            type(exc).__name__,
            exc_info=True,
        )
        block = _unknown(day)
    block["checked"] = all(
        value is not None for key, value in block.items() if key != "checked"
    )
    return {"theory": block}


def _unknown(day: date) -> dict[str, Any]:
    """The nine contract fields in order; every checkable one is cannot-check."""
    return {
        "checked": False,
        "day": day_key(day),
        "unit": None,
        "phase": None,
        "minutes_today": None,
        "minutes_into_credit": None,
        "minutes_per_credit": MINUTES_PER_CREDIT,
        "credits_today": None,
        "needed": None,
    }


def _block(moment: datetime, day: date, key_file: Path | None) -> dict[str, Any]:
    """Read the signed inputs; a ``None`` field is one that could not be read."""
    ledger = load_ledger(_constants.LEDGER_FILE, key_file=key_file)
    decision = decide_today(ledger, day=day, now=moment, key_file=key_file)
    block = _unknown(day)
    block["credits_today"], _ = theory_credits(ledger, day=day)
    block["needed"] = decision.needed
    state = gather_phase(ledger, key_file=key_file)
    if state is None:
        return block
    block["unit"], block["phase"] = state.unit, state.phase
    minutes = paying_minutes(state, ledger, day=day, key_file=key_file)
    block["minutes_today"] = minutes
    if minutes is not None:
        block["minutes_into_credit"] = minutes_into_credit(
            ledger, state, minutes, day=day
        )
    return block
