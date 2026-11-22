# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the Tk tooltip helper.

Stacking (the tip staying above a raised surface) needs a real X server:
``scripts/verify_tooltip_stack.py``. These pin the wiring around it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from leetcode_guard._tooltip import Tooltip, add_tooltip


def _widget(*, pointer: tuple[int, int] = (130, 240)) -> MagicMock:
    """A button inside a 600x300 surface whose top-left is at (100, 200)."""
    w = MagicMock()
    w.after.return_value = "job-id"
    w.winfo_pointerx.return_value = pointer[0]
    w.winfo_pointery.return_value = pointer[1]
    top = w.winfo_toplevel.return_value
    top.winfo_rootx.return_value = 100
    top.winfo_rooty.return_value = 200
    top.winfo_width.return_value = 600
    top.winfo_height.return_value = 300
    return w


def _handlers(w: MagicMock) -> dict[str, MagicMock]:
    """The bound handlers, by event name."""
    return {str(call.args[0]): call.args[1] for call in w.bind.call_args_list}


@pytest.fixture(name="label")
def _label(tk_mock: MagicMock) -> MagicMock:
    """The tip Label the helper builds, measuring 40x20."""
    built = tk_mock.Label.return_value
    built.winfo_reqwidth.return_value = 40
    built.winfo_reqheight.return_value = 20
    return built


def _hover_and_show(w: MagicMock) -> None:
    """Enter the widget and fire the scheduled show."""
    _handlers(w)["<Enter>"](None)
    w.after.call_args.args[1]()


def test_add_tooltip_returns_a_tooltip() -> None:
    """add_tooltip builds a Tooltip."""
    assert isinstance(add_tooltip(MagicMock(), "help"), Tooltip)


def test_tooltip_binds_enter_leave_and_press() -> None:
    """Hover shows it; leaving or clicking hides it."""
    w = MagicMock()
    Tooltip(w, "hint")
    assert set(_handlers(w)) == {"<Enter>", "<Leave>", "<ButtonPress>"}


def test_hover_shows_a_label_placed_inside_the_surface(
    tk_mock: MagicMock, label: MagicMock
) -> None:
    """The tip is a child of the button's toplevel, never a Toplevel of its own."""
    w = _widget()
    Tooltip(w, "go", delay_ms=0)
    _hover_and_show(w)
    tk_mock.Toplevel.assert_not_called()
    assert tk_mock.Label.call_args.args == (w.winfo_toplevel.return_value,)
    assert tk_mock.Label.call_args.kwargs["text"] == "go"
    label.place.assert_called_once_with(x=40, y=50)
    label.lift.assert_called_once_with()


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [((690, 490), {"x": 560, "y": 280}), ((50, 100), {"x": 0, "y": 0})],
)
def test_the_tip_is_kept_inside_the_surface(
    label: MagicMock, pointer: tuple[int, int], expected: dict[str, int]
) -> None:
    """Near an edge the tip is pulled back so it never draws off the surface."""
    w = _widget(pointer=pointer)
    Tooltip(w, "go", delay_ms=0)
    _hover_and_show(w)
    label.place.assert_called_once_with(**expected)


def test_a_second_enter_while_pending_schedules_nothing() -> None:
    """One pending show at a time."""
    w = _widget()
    Tooltip(w, "go")
    _handlers(w)["<Enter>"](None)
    _handlers(w)["<Enter>"](None)
    assert w.after.call_count == 1


@pytest.mark.usefixtures("label")
def test_a_shown_tip_is_not_shown_twice(tk_mock: MagicMock) -> None:
    """A visible tip is not built again."""
    w = _widget()
    Tooltip(w, "go", delay_ms=0)
    _hover_and_show(w)
    _hover_and_show(w)
    assert tk_mock.Label.call_count == 1


def test_leaving_cancels_a_pending_show() -> None:
    """Leaving before the delay cancels the show."""
    w = _widget()
    Tooltip(w, "go")
    _handlers(w)["<Enter>"](None)
    _handlers(w)["<Leave>"](None)
    w.after_cancel.assert_called_once_with("job-id")


def test_leaving_without_a_tip_is_harmless() -> None:
    """Nothing pending and nothing shown: a no-op."""
    w = _widget()
    Tooltip(w, "go")
    _handlers(w)["<Leave>"](None)
    w.after_cancel.assert_not_called()


def test_a_click_removes_a_visible_tip(label: MagicMock) -> None:
    """Pressing the button removes the tip."""
    w = _widget()
    Tooltip(w, "go", delay_ms=0)
    _hover_and_show(w)
    _handlers(w)["<ButtonPress>"](None)
    label.destroy.assert_called_once_with()
    w.after_cancel.assert_not_called()
