"""``--evening``: this gate as one rung of the evening chain.

When the shutdown time arrives with a rung unpaid, ``gatelock.evening_chain``
runs the gates one after another instead of entering night lockdown. This
module is leetcode-guard's half of that contract (``--production --evening``):

* **Decide = "is the rung paid today"**, not the gate's own ``decide``: a
  verified ``charge`` row with ``source == "leetcode"``
  (``earned_time.done_today(LEETCODE, ..., gate_off=False)``). That is the row
  the shutdown ladder pays +60 min for, so a day settled by the escape hatch or
  an outage (other sources) still shows the window.
* **Paid** exits 0 with no window and without waiting for X.
* **No X within** :data:`X_WAIT_SECONDS` exits :data:`EXIT_NO_X`: the chain
  must not hang behind a display that is not coming.
* **Ignored on purpose:** the morning-session carrot, tonight's night-lockdown
  stand-down, and the first-run seeding deferral. Each makes ``cmd_lock``
  return 0 on an unpaid rung, and the orchestrator would relaunch it forever.
  Free and sick days are the orchestrator's call, not this gate's.

Fail closed: a ledger or key that cannot be read is "could not check", logged,
and the rung counts as unpaid -- the window stays up.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from typing import TYPE_CHECKING, Final

import earned_time
from gatelock import log_integrity, wait_for_x_server

from leetcode_guard._constants import EXIT_OK

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

X_WAIT_SECONDS: Final = 10.0
"""The bounded display wait; the contract allows at most 10 s."""

EXIT_NO_X: Final = 3
"""No X server answered in time: nothing was shown, nothing was decided."""

_CONTRACT_END_EVENING: Final = 10
"""Exit code of the end-evening control; mirrors ``evening-chain/CONTRACT.md``."""


def end_evening_code() -> int:
    """The orchestrator's own constant when it exists, else the contract's.

    ``gatelock.evening_chain`` ships separately; looking for it first keeps this
    package importable against a gatelock that predates it.
    """
    if importlib.util.find_spec("gatelock.evening_chain") is None:
        return _CONTRACT_END_EVENING
    chain = importlib.import_module("gatelock.evening_chain")
    return int(getattr(chain, "EXIT_END_EVENING", _CONTRACT_END_EVENING))


EXIT_END_EVENING: Final = end_evening_code()
"""Exit code meaning "kuhy ended the evening": the chain stops, lockdown follows."""


def evening_paid(
    ledger_path: Path, *, key_file: Path | None, now: datetime | None = None
) -> bool:
    """Whether today's leetcode rung is verifiably paid. Unreadable means no."""
    key = key_file if key_file is not None else log_integrity.DEFAULT_HMAC_KEY_FILE
    try:
        paid = earned_time.done_today(
            earned_time.LEETCODE, ledger_path, key, now=now, gate_off=False
        )
    except OSError, ValueError:
        _logger.exception("evening: could not check %s; unpaid", ledger_path)
        return False
    if paid is None:
        _logger.warning("evening: could not check %s; unpaid", ledger_path)
        return False
    return paid


def evening_preflight(ledger_path: Path) -> int | None:
    """Exit code if the evening run ends before any window, else ``None``."""
    if evening_paid(ledger_path, key_file=None):
        sys.stdout.write("evening: today's leetcode rung is already paid\n")
        return EXIT_OK
    if not wait_for_x_server(timeout_s=X_WAIT_SECONDS):
        sys.stderr.write(f"evening: no X server within {X_WAIT_SECONDS:.0f} s\n")
        return EXIT_NO_X
    return None
