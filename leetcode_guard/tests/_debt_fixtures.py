"""Fixtures for the missed-day debt rule.

A pytest plugin rather than more lines in ``conftest.py``, which sits at the
250-line cap. Registered there via ``pytest_plugins``.
"""

from __future__ import annotations

from datetime import date
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _no_sick_days_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never let the gate read the developer's real sick-day pool.

    The twin of ``_no_free_days_by_default``: a real sick day marked on this
    machine would silently stand the gate down in every scenario below.
    """
    import sickdays
    import sickdays._api
    import sickdays._keep_api

    isolated = sickdays.Paths.under(tmp_path / "sickdays")
    # Reads (is_sick_day, stands_down, kept_lockers) go through _api.load;
    # set_kept_lockers binds its own resolve_paths in _keep_api.
    for module in (sickdays._api, sickdays._keep_api):
        monkeypatch.setattr(module, "resolve_paths", lambda paths: paths or isolated)


@pytest.fixture(autouse=True)
def _no_debt_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the debt rule off for every test that is not about it.

    ``_gate_in_force`` moves ``GATE_START_DATE`` back to 2000, so without this
    every scenario would owe a quarter-century of missed days and the whole
    suite would quietly start testing something else. An epoch of
    ``date.max`` makes the window empty. Tests that are about debt use
    :func:`debt_starts`.
    """
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("leetcode_guard.") and hasattr(
            module, "DEBT_START_DATE"
        ):
            monkeypatch.setattr(module, "DEBT_START_DATE", date.max, raising=True)


@pytest.fixture
def debt_starts(monkeypatch: pytest.MonkeyPatch):
    """Put the debt epoch where a test wants it: ``debt_starts(MONDAY)``.

    Counterpart to ``_no_debt_by_default``. Returns a callable so the epoch
    is chosen inside the test, next to the days it reasons about.
    """
    from leetcode_guard import _debt

    def _set(day: date) -> date:
        monkeypatch.setattr(_debt, "DEBT_START_DATE", day)
        return day

    return _set
