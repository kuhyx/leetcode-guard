"""``python3 -m leetcode_guard.open_cli``: the first cached suggestion, in a browser.

The daily-limits popup starts it when its LeetCode row is clicked and reads
only the exit status, so the status is the contract: 0 means a browser was
started, anything else means the click opened nothing.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

from leetcode_guard import _browser, open_cli
from leetcode_guard._browser import LaunchResult
from leetcode_guard._phase_view import PhaseView

if TYPE_CHECKING:
    import pytest

FIRST = "https://leetcode.com/problems/two-sum/"
SECOND = "https://leetcode.com/problems/add-two-numbers/"
NONE_VIEW = PhaseView(
    unit="",
    phase="none",
    learn_target=None,
    lessons_ready=False,
    solved=0,
    total=0,
    cards_taught=None,
    cards_total=None,
    theory_minutes_today=0,
    minutes_per_credit=12,
)
"""Every unit finished: the lock's first action is its first problem."""


def _cache(
    monkeypatch: pytest.MonkeyPatch, *urls: str, view: PhaseView = NONE_VIEW
) -> list[int]:
    """Serve ``urls`` as the cached suggestions; returns the limits asked for."""
    limits: list[int] = []

    def gather(*, limit: int) -> SimpleNamespace:
        limits.append(limit)
        rows = [SimpleNamespace(url=url) for url in urls]
        return SimpleNamespace(
            pool=SimpleNamespace(suggestions=rows), unit=SimpleNamespace(view=view)
        )

    monkeypatch.setattr(open_cli, "gather_status", gather)
    return limits


def _launcher(monkeypatch: pytest.MonkeyPatch, *, ok: bool) -> list[str]:
    """Replace the launcher; returns the URLs it was asked to open."""
    opened: list[str] = []

    def launch(url: str) -> LaunchResult:
        opened.append(url)
        return LaunchResult(ok=ok, reason="opened" if ok else "no launcher")

    monkeypatch.setattr(_browser, "launch", launch)
    return opened


def test_it_opens_the_first_suggestion_and_exits_zero(monkeypatch: pytest.MonkeyPatch):
    """Only the first row is opened, and only one row is asked for."""
    limits = _cache(monkeypatch, FIRST, SECOND)
    opened = _launcher(monkeypatch, ok=True)

    assert open_cli.main() == open_cli.EXIT_OPENED == 0
    assert opened == [FIRST]
    assert limits == [1]


def test_an_empty_cache_opens_nothing_and_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """No suggestion is a failed click, never a silent success."""
    _cache(monkeypatch)
    opened = _launcher(monkeypatch, ok=True)

    with caplog.at_level(logging.WARNING):
        assert open_cli.main() == open_cli.EXIT_NOTHING == 1
    assert opened == []
    assert "nothing to open" in caplog.text


def test_a_browser_that_did_not_start_exits_nonzero(monkeypatch: pytest.MonkeyPatch):
    """The launcher's own failure reaches the caller as the exit status."""
    _cache(monkeypatch, FIRST)
    opened = _launcher(monkeypatch, ok=False)

    assert open_cli.main() == open_cli.EXIT_NOTHING
    assert opened == [FIRST]
