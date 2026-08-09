"""Tests for the study-mode strip.

Tk is a MagicMock, so these assert on what was asked of Tk. The placement test
uses two outputs on purpose: against a single output a bug that always picked
surface zero would pass.
"""

from __future__ import annotations

import logging
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._study_strip import StripText, StudyStrip, build_strip

CONFIG = LockConfig()


def rect(x: int = 0, y: int = 0, width: int = 1920, height: int = 1080):
    return SimpleNamespace(x=x, y=y, width=width, height=height)


def build(*, on_back=None, at=None) -> StudyStrip:
    return build_strip(
        MagicMock(),
        CONFIG,
        StripText(elapsed_seconds=0.0, needed=1),
        rect=at if at is not None else rect(),
        on_back=on_back or (lambda: None),
    )


def index_of(calls, needle: str) -> int:
    for position, call in enumerate(calls):
        if call[0] == needle:
            return position
    seen = [c[0] for c in calls]
    message = f"{needle} not called; got {seen}"
    raise AssertionError(message)


# -- text ------------------------------------------------------------------


def test_the_elapsed_line_counts_up_and_never_down():
    """No deadline exists, so no countdown may be implied. Study mode ends on a
    solve or on the button -- inventing a timer would invent a pressure the
    gate does not actually apply."""
    text = StripText(elapsed_seconds=902.0, needed=1)

    assert text.elapsed == "Studying for 15:02"
    for forbidden in ("remaining", "left", "until", "deadline"):
        assert forbidden not in text.elapsed.lower()


def test_the_elapsed_line_survives_a_clock_that_went_backwards():
    assert StripText(elapsed_seconds=-5.0, needed=1).elapsed == "Studying for 00:00"


def test_the_owed_line_is_singular_for_one():
    assert StripText(elapsed_seconds=0, needed=1).owed == (
        "Still need 1 accepted submission"
    )


def test_the_owed_line_is_plural_for_more():
    assert StripText(elapsed_seconds=0, needed=3).owed == (
        "Still need 3 accepted submissions"
    )


# -- construction ----------------------------------------------------------


def test_overrideredirect_is_set_before_the_geometry(tk_mock):
    """Set after mapping it is ignored, and the strip lands wherever the window
    manager feels like putting it."""
    build()

    calls = tk_mock.Toplevel.return_value.mock_calls
    assert index_of(calls, "withdraw") < index_of(calls, "overrideredirect")
    assert index_of(calls, "overrideredirect") < index_of(calls, "geometry")
    assert index_of(calls, "geometry") < index_of(calls, "deiconify")


def test_it_asks_to_stay_on_top(tk_mock):
    build()

    tk_mock.Toplevel.return_value.attributes.assert_called_with("-topmost", 1)


def test_it_sits_on_the_rectangle_it_was_given_not_the_whole_x_screen(tk_mock):
    """The root spans every display, so screen-width arithmetic would park this
    on the far monitor of a two-monitor desk."""
    build(at=rect(x=1920, y=0, width=2560, height=1440))

    geometry = tk_mock.Toplevel.return_value.geometry.call_args[0][0]
    _size, _, offset = geometry.partition("+")
    assert offset.startswith("41")  # 1920 + 2560 - 320 - 16 = 4144


def test_the_back_button_is_wired_and_is_not_styled_as_destructive(tk_mock):
    """Returning to the lock is the ordinary path; danger belongs to the
    escape hatch."""
    pressed: list[str] = []
    build(on_back=lambda: pressed.append("back"))

    back = next(
        call
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == "Back to lock"
    )
    back.kwargs["command"]()

    assert pressed == ["back"]
    assert back.kwargs["bg"] == CONFIG.accent
    assert back.kwargs["bg"] != CONFIG.danger


def test_it_says_what_it_is_and_what_is_owed(tk_mock):
    build()

    texts = [str(call.kwargs.get("text", "")) for call in tk_mock.Label.call_args_list]
    assert any("Study mode" in text for text in texts)
    assert any("Studying for" in text for text in texts)
    assert any("Still need" in text for text in texts)


# -- ticking ---------------------------------------------------------------


def test_the_tick_refreshes_the_labels_and_re_lifts():
    """Nothing else is keeping this on top: the recovery loop is stopped, which
    is the entire reason study mode works at all."""
    strip = build()

    strip.tick(StripText(elapsed_seconds=61.0, needed=2))

    # Both labels are the same shared mock, so read the calls rather than
    # expecting two distinct widgets.
    written = {
        call.kwargs.get("text")
        for call in strip._elapsed_label.configure.call_args_list
    }
    assert "Studying for 01:01" in written
    assert "Still need 2 accepted submissions" in written
    strip.window.lift.assert_called()


def test_scheduling_drives_the_tick_from_a_supplier():
    strip = build()
    strip.window.after = MagicMock(side_effect=lambda _ms, fn: fn() or "job")

    calls = {"n": 0}

    def supply() -> StripText:
        calls["n"] += 1
        if calls["n"] > 2:
            strip._destroyed = True
        return StripText(elapsed_seconds=float(calls["n"]), needed=1)

    strip.schedule(supply)

    assert calls["n"] >= 2


def test_a_tick_after_destroy_does_nothing():
    strip = build()
    strip.destroy()
    strip._elapsed_label.reset_mock()

    strip.tick(StripText(elapsed_seconds=1.0, needed=1))

    strip._elapsed_label.configure.assert_not_called()


def test_scheduling_after_destroy_does_nothing():
    strip = build()
    strip.destroy()
    strip.window.after.reset_mock()

    strip.schedule(lambda: StripText(elapsed_seconds=0.0, needed=1))

    strip.window.after.assert_not_called()


def test_a_tick_that_raises_stops_the_strip_rather_than_the_lock(caplog):
    """A raised exception inside a Tk callback while the lock is stood down is
    not something to find out about later."""
    strip = build()
    strip.window.lift.side_effect = tk.TclError("window is gone")

    with caplog.at_level(logging.WARNING):
        strip.tick(StripText(elapsed_seconds=1.0, needed=1))

    assert strip._destroyed is True
    assert caplog.records


# -- teardown --------------------------------------------------------------


def test_destroy_cancels_the_tick_and_the_window():
    strip = build()
    strip._job = "job-1"

    strip.destroy()

    strip.window.after_cancel.assert_called_once_with("job-1")
    strip.window.destroy.assert_called_once()


def test_destroy_is_idempotent():
    strip = build()

    strip.destroy()
    strip.destroy()

    strip.window.destroy.assert_called_once()


def test_a_destroy_that_raises_is_logged_not_propagated(caplog):
    strip = build()
    strip.window.destroy.side_effect = tk.TclError("already gone")

    with caplog.at_level(logging.WARNING):
        strip.destroy()

    assert caplog.records
