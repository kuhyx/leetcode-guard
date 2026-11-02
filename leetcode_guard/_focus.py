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
    from types import ModuleType

GATE: Final = "leetcode"
"""The gate name ``focus_project`` knows this gate by."""

GENERIC_NAME: Final = "focus project"

_logger = logging.getLogger(__name__)
_warned: set[str] = set()
"""Which failures were already logged: one line per process, not per day."""


def _module() -> ModuleType | None:
    """The ``focus_project`` package, or None (logged once) when not importable."""
    try:
        return importlib.import_module("focus_project")
    except ImportError:
        if "import" not in _warned:
            _warned.add("import")
            _logger.exception(
                "focus_project is not importable: not standing down for a "
                "focus project (the gate applies as before)"
            )
        return None


def stands_down(gate: str, day: date) -> bool:
    """Whether an active focus project replaces ``gate`` on ``day``."""
    module = _module()
    return module is not None and bool(module.stands_down(gate, day))


def project_name(day: date) -> str:
    """The name of the focus project active on ``day`` (for status text).

    Only asked on a day :func:`stands_down` already said yes to; a package
    that cannot say falls back to a generic name rather than hiding the day.
    """
    module = _module()
    project = None if module is None else module.active(day)
    return GENERIC_NAME if project is None else str(project.name)


def label(gate: str, day: date) -> str | None:
    """The focus project's name when it stands ``gate`` down on ``day``."""
    return project_name(day) if stands_down(gate, day) else None
