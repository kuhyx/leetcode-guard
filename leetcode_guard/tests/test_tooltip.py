# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the Tk tooltip helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from leetcode_guard._tooltip import Tooltip, add_tooltip


def _make_parent() -> MagicMock:
    """A minimally-Tk parent with after/winfo_* wired on a mock."""
    p = MagicMock()
    p.after = MagicMock(return_value="job-id")
    p.winfo_pointerx = MagicMock(return_value=100)
    p.winfo_pointery = MagicMock(return_value=200)
    return p


def _handlers(w: MagicMock) -> dict[str, MagicMock]:
    """Extract bound handlers from a widget's bind call_args_list."""
    return {str(call.args[0]): call.args[1] for call in w.bind.call_args_list}


def test_add_tooltip_returns_a_tooltip() -> None:
    """add_tooltip constructs and returns a Tooltip instance."""
    assert isinstance(add_tooltip(MagicMock(), "help"), Tooltip)


def test_tooltip_registers_enter_and_leave_bindings() -> None:
    """Adding a tooltip binds <Enter>, <Leave> and <ButtonPress>."""
    w = MagicMock()
    Tooltip(w, "hint")
    assert w.bind.call_count == 3
    events = [str(call.args[0]) for call in w.bind.call_args_list]
    assert "<Enter>" in events
    assert "<Leave>" in events
    assert "<ButtonPress>" in events


def test_hover_schedules_a_delayed_show() -> None:
    """Hover enters a binding that schedules _show after delay_ms."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=0)
        handlers = _handlers(w)
        handlers["<Enter>"](None)
        # Execute the scheduled callback.
        cb = w.after.call_args.args[1]
        cb()
    assert tip_tk.wm_geometry.called
    assert tip_tk.wm_overrideredirect.called


def test_topmost_attribute_is_set_on_the_tip_window() -> None:
    """The tip is forced above the lock window with -topmost."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=0)
        handlers = _handlers(w)
        handlers["<Enter>"](None)
        cb = w.after.call_args.args[1]
        cb()
    tip_tk.attributes.assert_called_once_with("-topmost", 1)


def test_double_enter_schedules_only_once() -> None:
    """Two rapid <Enter> events produce exactly one scheduled show."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=0)
        handlers = _handlers(w)
        handlers["<Enter>"](None)
        cb = w.after.call_args.args[1]
        cb()
        # Second <Enter> should be a no-op since _tip is already set.
        handlers["<Enter>"](None)
    # Only one Toplevel should be constructed despite two <Enter> events.
    assert tip_tk.wm_geometry.call_count == 1


def test_leaving_cancels_any_scheduled_show_and_destroys_tip() -> None:
    """Exit hides the tip immediately and clears the timer job."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.after_cancel = MagicMock()
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    tip_tk.destroy = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=500)
        handlers = _handlers(w)
        # Trigger <Enter> to schedule a show, then trigger <Leave>
        # BEFORE the callback fires - this tests that a scheduled show
        # gets cancelled.
        handlers["<Enter>"](None)
        handlers["<Leave>"](None)
    w.after_cancel.assert_called_once_with("job-id")
    # The tip was never created since we left before the callback.
    tip_tk.destroy.assert_not_called()


def test_leaving_without_an_open_tip_is_harmless() -> None:
    """No scheduled show and no tip to destroy: no-op."""
    w = MagicMock()
    w.after = MagicMock()
    w.after_cancel = MagicMock()
    Tooltip(w, "go")
    handlers = _handlers(w)
    handlers["<Leave>"](None)
    w.after_cancel.assert_not_called()


def test_button_press_hides_a_visible_tip() -> None:
    """Pressing any button closes an open tooltip."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.after_cancel = MagicMock()
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    tip_tk.destroy = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go")
        handlers = _handlers(w)
        handlers["<Enter>"](None)
        cb = w.after.call_args.args[1]
        cb()
        # Now the tip is open; trigger <ButtonPress>.
        handlers["<ButtonPress>"](None)
    # After callback fires, _job is None, so after_cancel is not called.
    # But tip is open, so destroy is called.
    tip_tk.destroy.assert_called_once()


def test_schedule_early_return_when_job_already_pending() -> None:
    """If a job is already scheduled, a second Enter does nothing."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=0)
        handlers = _handlers(w)
        # First <Enter> schedules a show.
        handlers["<Enter>"](None)
        # A second <Enter> should be silently ignored (early return).
        handlers["<Enter>"](None)
    # after was called only once.
    assert w.after.call_count == 1


def test_show_early_return_when_tip_already_open() -> None:
    """Calling _show while a tip is already visible makes no second Toplevel."""
    parent = _make_parent()
    w = MagicMock()
    w.after = parent.after
    w.winfo_pointerx = parent.winfo_pointerx
    w.winfo_pointery = parent.winfo_pointery
    tip_tk = MagicMock()
    tip_tk.wm_overrideredirect = MagicMock()
    tip_tk.attributes = MagicMock()
    tip_tk.wm_geometry = MagicMock()
    tip_tk.pack = MagicMock()
    with patch("leetcode_guard._tooltip.tk.Toplevel", return_value=tip_tk):
        Tooltip(w, "go", delay_ms=0)
        handlers = _handlers(w)
        # First hover creates the tip.
        handlers["<Enter>"](None)
        cb = w.after.call_args.args[1]
        cb()
        # Second hover while tip is open should be ignored.
        handlers["<Enter>"](None)
        cb2 = w.after.call_args.args[1]
        cb2()
    # Only one Toplevel created despite two shows.
    assert tip_tk.wm_geometry.call_count == 1
