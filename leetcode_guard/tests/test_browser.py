"""Tests for the browser launcher.

Nothing here forks: ``spawn`` is injected everywhere, and ``filterwarnings =
["error"]`` would turn a stray real ``Popen`` into a suite failure anyway.
"""

from __future__ import annotations

import logging

from leetcode_guard._browser import OPENERS, LaunchResult, find_opener, launch


class _Recorder:
    """Stands in for ``subprocess.Popen`` and remembers how it was called."""

    def __init__(self, *, fail: OSError | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []
        self._fail = fail

    def __call__(self, args, *, start_new_session):
        self.calls.append((tuple(args), start_new_session))
        if self._fail is not None:
            raise self._fail
        return object()


def _only(monkeypatch, available: dict[str, str | None]):
    """Make ``shutil.which`` answer from a fixed table."""
    monkeypatch.setattr("leetcode_guard._browser.shutil.which", available.get)


def test_the_desktop_default_wins_when_it_exists(monkeypatch):
    _only(monkeypatch, {"xdg-open": "/usr/bin/xdg-open", "firefox": "/usr/bin/firefox"})

    assert find_opener() == "/usr/bin/xdg-open"


def test_it_falls_back_when_the_desktop_default_is_missing(monkeypatch):
    """A bare X session with no xdg-utils still gets a browser."""
    _only(monkeypatch, {"firefox": "/usr/bin/firefox"})

    assert find_opener() == "/usr/bin/firefox"


def test_no_opener_at_all_is_reported_not_raised(monkeypatch, caplog):
    _only(monkeypatch, {})

    with caplog.at_level(logging.WARNING):
        result = launch("https://leetcode.com/problems/two-sum/")

    assert result.ok is False
    assert find_opener() is None
    for candidate in OPENERS:
        assert candidate in result.reason
    assert caplog.records


def test_the_url_is_passed_through_untouched(monkeypatch):
    """A list, never a shell string: no quoting, no word splitting, no way for
    a problem slug to become an argument."""
    _only(monkeypatch, {"xdg-open": "/usr/bin/xdg-open"})
    spawn = _Recorder()
    url = "https://leetcode.com/problems/two-sum/"

    result = launch(url, spawn=spawn)

    assert result.ok is True
    assert spawn.calls[0][0] == ("/usr/bin/xdg-open", url)
    assert result.command == ("/usr/bin/xdg-open", url)


def test_the_browser_is_detached_so_stopping_the_service_cannot_kill_it(monkeypatch):
    """``start_new_session=True`` is the whole reason the break-glass command
    printed on the lock does not also close the tab the user is solving in. A
    well-meaning simplification deletes this; the assertion is here to stop it.
    """
    _only(monkeypatch, {"xdg-open": "/usr/bin/xdg-open"})
    spawn = _Recorder()

    launch("https://leetcode.com/problems/two-sum/", spawn=spawn)

    assert spawn.calls[0][1] is True


def test_an_opener_that_vanishes_mid_launch_is_reported(monkeypatch, caplog):
    """``which`` said yes and the exec said no -- a real race on an updating
    system, and not a reason to take the lock down with it."""
    _only(monkeypatch, {"xdg-open": "/usr/bin/xdg-open"})
    spawn = _Recorder(fail=OSError("No such file or directory"))

    with caplog.at_level(logging.ERROR):
        result = launch("https://leetcode.com/problems/two-sum/", spawn=spawn)

    assert result.ok is False
    assert "could not be started" in result.reason
    assert result.command == (
        "/usr/bin/xdg-open",
        "https://leetcode.com/problems/two-sum/",
    )
    assert caplog.records


def test_a_launch_result_says_which_opener_ran(monkeypatch):
    _only(monkeypatch, {"x-www-browser": "/usr/bin/x-www-browser"})

    result = launch("https://example.invalid/", spawn=_Recorder())

    assert isinstance(result, LaunchResult)
    assert "x-www-browser" in result.reason


def test_a_null_byte_in_the_url_is_reported_not_raised(monkeypatch, caplog):
    """The slug comes from LeetCode's JSON and nothing validates it, so a NUL
    reaches `Popen`, which rejects it with ValueError -- not an OSError. That
    escaped `launch` and did so *after* study mode released the grab, leaving
    the machine open on a malformed API response. "Never raises" is load-bearing
    here, so it has to be true."""
    _only(monkeypatch, {"xdg-open": "/usr/bin/xdg-open"})

    with caplog.at_level(logging.ERROR):
        result = launch("https://leetcode.com/problems/two-sum\x00evil/")

    assert result.ok is False
    assert "null byte" in result.reason
    assert caplog.records
