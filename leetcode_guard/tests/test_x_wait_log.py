"""The lock's wait for an X server logs the first refusal, then slowly.

2026-11-22 09:00-10:09: the timer's run waited 70 minutes on an X server that
refused it, and the journal got "Authorization required, but no authorization
protocol specified" 8378 times. libX11 writes that to fd 2 itself, inside
``tk.Tk()``, on every one-second attempt; no Python log call is involved, so a
log filter cannot catch it. The wait itself stays unbounded (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import functools
import importlib.util
import logging
import os
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import gatelock

from leetcode_guard import _cli

if TYPE_CHECKING:
    import pytest

REFUSAL = b"Authorization required, but no authorization protocol specified\n"
REFUSED_ATTEMPTS = 4200
"""One per second, 70 minutes: what the 09:00 run went through."""
LINE_BUDGET = 20
"""First refusal + one heartbeat per 300 s (14) + "answered", with slack."""


@dataclass
class Clock:
    """A fake monotonic clock that the wait's ``sleep`` advances."""

    now_s: float = 0.0

    def sleep(self, seconds: float) -> None:
        """Advance instead of blocking."""
        self.now_s += seconds

    def monotonic(self) -> float:
        """The fake time."""
        return self.now_s


@dataclass
class RefusingDisplay:
    """``tk.Tk`` as libX11 behaves against a server that refuses the cookie."""

    refusals: int
    calls: int = field(default=0)

    def __call__(self) -> MagicMock:
        """Write the refusal to fd 2 twice, like libX11, then fail."""
        self.calls += 1
        if self.calls <= self.refusals:
            os.write(2, REFUSAL)
            os.write(2, REFUSAL)
            message = 'couldn\'t connect to display ":0"'
            raise tk.TclError(message)
        return MagicMock()


def _arm_refusing_x(monkeypatch: pytest.MonkeyPatch, display: RefusingDisplay) -> None:
    clock = Clock()
    monkeypatch.setattr(tk, "Tk", display)
    if importlib.util.find_spec("leetcode_guard._x_probe") is not None:
        # The guard's own probe; the Tk stub replaced its ``tk`` with a mock.
        monkeypatch.setattr("leetcode_guard._x_probe.tk.Tk", display)
    monkeypatch.setattr(
        _cli,
        "wait_for_x_server",
        functools.partial(
            gatelock.wait_for_x_server, sleep=clock.sleep, monotonic=clock.monotonic
        ),
    )
    # Stop right after the wait: the instance lock says another run is up.
    monkeypatch.setattr(_cli, "acquire_instance", lambda _path: None)


def test_x_wait_refused_for_70_minutes_logs_a_bounded_number_of_lines(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """8378 lines on 2026-11-22; a handful now, and the wait still ends."""
    display = RefusingDisplay(refusals=REFUSED_ATTEMPTS)
    _arm_refusing_x(monkeypatch, display)

    with caplog.at_level(logging.WARNING):
        _cli.cmd_lock(demo_mode=False)

    err = capfd.readouterr().err
    refusal_lines = err.count(REFUSAL.decode())
    lines = len(err.splitlines()) + len(caplog.records)
    assert display.calls == REFUSED_ATTEMPTS + 1, "the wait must outlast every refusal"
    assert lines <= LINE_BUDGET, f"{lines} lines ({refusal_lines} raw refusals)"


def test_x_wait_names_the_refusal_once_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Quiet is not silent: the first refusal's own text reaches the journal."""
    _arm_refusing_x(monkeypatch, RefusingDisplay(refusals=3))

    with caplog.at_level(logging.WARNING):
        _cli.cmd_lock(demo_mode=False)

    logged = [r.getMessage() for r in caplog.records]
    named = [m for m in logged if "Authorization required" in m]
    assert len(named) == 1, logged
    assert "\n" not in named[0], "one refusal, one journal line"
    assert REFUSAL.decode() not in capfd.readouterr().err
