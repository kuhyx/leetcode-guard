"""Shared fixtures for the study-mode tests.

**Ordering is the whole feature**, so most of the tests assert *when* a call
happened, not just that it did. The technique lives in :func:`wired` and
:func:`index_of`: hang every collaborator off one parent ``MagicMock``, then
read ``parent.mock_calls``, which records calls across all children in global
order. Asserting "recovery stopped" and "grab released" separately would pass
against code that does them in the wrong order, which is exactly the bug that
would make the whole feature a no-op.

No real Tk and no X: the failures are driven by ``side_effect``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._study import StudySession

PRODUCTION = LockConfig(mode="hard")
DEMO = LockConfig(mode="hard", grab="local", disable_vt=False)


class _Rect:
    def __init__(self, spec: str = "1920x1080+0+0") -> None:
        self._spec = spec

    def geometry(self) -> str:
        return self._spec


def _info(name: str, *, index: int = 0, primary: bool = True):
    return SimpleNamespace(
        output_name=name, rect=_Rect(), index=index, is_primary=primary
    )


def wired(*outputs: str):
    """A parent mock plus a lock whose calls all record into it."""
    parent = MagicMock()
    lock = parent.lock
    names = outputs or ("DP-0",)
    infos = tuple(
        _info(name, index=i, primary=(i == 0)) for i, name in enumerate(names)
    )
    lock.surfaces.infos.return_value = infos
    lock.surfaces._surfaces = {
        info.output_name: SimpleNamespace(
            info=info, window=getattr(parent, f"surf_{info.output_name}")
        )
        for info in infos
    }
    return parent, lock


def session(lock, config=PRODUCTION, *, clock=None, on_fail=None) -> StudySession:
    ticks = iter(clock or [0.0, 0.0, 0.0, 0.0, 0.0])
    return StudySession(
        lock,
        config,
        on_fail_closed=on_fail or (lambda _reason: None),
        now=lambda: next(ticks, 0.0),
    )


def index_of(calls, needle: str) -> int:
    """Position of the first recorded call whose name matches exactly."""
    for position, call in enumerate(calls):
        if call[0] == needle:
            return position
    seen = [c[0] for c in calls]
    message = f"{needle} was never called; got {seen}"
    raise AssertionError(message)
