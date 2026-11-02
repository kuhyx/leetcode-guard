"""Focus-project stand-down: a declared project switches this gate off.

``focus_project.stands_down("leetcode", day)`` is True while an active focus
project replaces LeetCode. The gate then treats the day exactly like a sick day
that does not keep it: no price, no charge, no debt owed, no lock.

Fail closed: if ``focus_project`` cannot be imported the gate behaves as it did
before the package existed (NOT standing down) and the error is logged, once
per process. The module is looked up at call time, never from-imported, so the
suite can replace ``stands_down`` on it.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import date

GATE: Final = "leetcode"
"""The gate name ``focus_project`` knows this gate by."""

_logger = logging.getLogger(__name__)
_warned: set[str] = set()
"""Which failures were already logged: one line per process, not per day."""


def stands_down(gate: str, day: date) -> bool:
    """Whether an active focus project replaces ``gate`` on ``day``."""
    try:
        module = importlib.import_module("focus_project")
    except ImportError:
        if "import" not in _warned:
            _warned.add("import")
            _logger.exception(
                "focus_project is not importable: not standing down for a "
                "focus project (the gate applies as before)"
            )
        return False
    return bool(module.stands_down(gate, day))
