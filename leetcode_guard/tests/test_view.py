"""Tests for the widget layer and the escape form.

Tk is a MagicMock here, so these assert on *what was asked of Tk* rather than
on pixels. The pixel check is the Xvfb screenshot in the verification steps --
which is how the demo close button being drawn behind the surface was found,
since no assertion here could have caught it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._breakglass import STOP_COMMAND
from leetcode_guard._view import GuardView, build_guard_view
from leetcode_guard._view_group import FrameGroup, WidgetGroup
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import ProblemLine, ViewModel

CONFIG = LockConfig()


def model(**kwargs) -> ViewModel:
    base = {
        "headline": "Solve 1 LeetCode problem to unlock",
        "balance_line": "Credits 0  |  Monday costs 1",
        "status_line": "Watching...",
        "notes": ("a note",),
        "problems": (ProblemLine(label="1. Two Sum", url="https://x/"),),
        "unlocked": False,
        "show_escape": False,
    }
    base.update(kwargs)
    return ViewModel(**base)


# -- WidgetGroup / FrameGroup ---------------------------------------------


def test_widget_group_mirrors_every_operation():
    widgets = [MagicMock(), MagicMock()]
    group = WidgetGroup(widgets)

    group.configure(text="x")
    group.pack(pady=1)
    group.pack_forget()

    for widget in widgets:
        widget.configure.assert_called_once_with(text="x")
        widget.pack.assert_called_once_with(pady=1)
        widget.pack_forget.assert_called_once()


def test_widget_group_destroy_clears_the_group():
    widgets = [MagicMock()]
    group = WidgetGroup(widgets)

    group.destroy()

    widgets[0].destroy.assert_called_once()
    assert len(group) == 0
    assert group.first is None


def test_widget_group_first_and_iteration():
    first, second = MagicMock(), MagicMock()
    group = WidgetGroup([first, second])

    assert group.first is first
    assert list(group) == [first, second]
    assert len(group) == 2


def test_frame_group_add_get_discard_clear():
    group = FrameGroup()
    frame = MagicMock()

    group.add("DP-0", frame)
    assert group.get("DP-0") is frame
    assert group.names == ("DP-0",)
    assert len(group) == 1
    assert list(group) == [frame]

    group.discard("DP-0")
    assert group.get("DP-0") is None

    group.add("HDMI-0", frame)
    group.clear()
    assert group.names == ()


def test_discarding_an_unknown_output_is_harmless():
    group = FrameGroup()

    group.discard("nope")

    assert group.names == ()


# -- build_guard_view ------------------------------------------------------


def test_a_view_is_built_for_one_surface():
    view = build_guard_view(MagicMock(), CONFIG, model(), output_name="DP-0")

    assert isinstance(view, GuardView)
    assert view.output_name == "DP-0"
    assert view.escape_button is None
    assert len(view.problem_labels) == 1


def test_an_empty_pool_gets_a_placeholder_rather_than_nothing():
    """A lock screen offering nothing at all is a dead end."""
    view = build_guard_view(MagicMock(), CONFIG, model(problems=()), output_name="DP-0")

    assert len(view.problem_labels) == 1


def test_the_escape_button_is_built_but_hidden_until_offered():
    view = build_guard_view(
        MagicMock(),
        CONFIG,
        model(show_escape=False),
        output_name="DP-0",
        on_escape=lambda: None,
    )

    assert view.escape_button is not None
    view.escape_button.pack_forget.assert_called_once()


def test_the_escape_button_stays_packed_when_offered():
    view = build_guard_view(
        MagicMock(),
        CONFIG,
        model(show_escape=True),
        output_name="DP-0",
        on_escape=lambda: None,
    )

    view.escape_button.pack_forget.assert_not_called()


# -- the Open control ------------------------------------------------------


def _three() -> ViewModel:
    return model(
        problems=tuple(
            ProblemLine(label=f"{n}. Problem {n}", url=f"https://leetcode.com/p{n}/")
            for n in (1, 2, 3)
        )
    )


def test_every_problem_gets_a_control_that_opens_it():
    """The 2026-08-05 lock named problems and offered no way to reach one."""
    view = build_guard_view(
        MagicMock(), CONFIG, _three(), output_name="DP-0", on_open=lambda _url: None
    )

    assert len(view.open_buttons) == 3


def test_each_open_button_carries_its_own_url(tk_mock):
    """A bare closure over the loop variable would give every button the *last*
    URL, and a count-based assertion cannot see that. So press each one."""
    opened: list[str] = []
    build_guard_view(
        MagicMock(), CONFIG, _three(), output_name="DP-0", on_open=opened.append
    )

    commands = [
        call.kwargs["command"]
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == "Open"
    ]
    for command in commands:
        command()

    assert opened == [
        "https://leetcode.com/p1/",
        "https://leetcode.com/p2/",
        "https://leetcode.com/p3/",
    ]


def test_without_the_callback_the_list_stays_inert():
    """Read-only renders (the fit harness, any future preview) must still work."""
    view = build_guard_view(MagicMock(), CONFIG, _three(), output_name="DP-0")

    assert view.open_buttons == []
    assert len(view.problem_labels) == 3


def test_the_url_is_not_printed_beside_the_button(tk_mock):
    """It was only ever there because nothing was clickable, and the second line
    it cost is what pushed the surface past its 768px budget."""
    build_guard_view(
        MagicMock(), CONFIG, _three(), output_name="DP-0", on_open=lambda _url: None
    )

    texts = [str(call.kwargs.get("text", "")) for call in tk_mock.Label.call_args_list]
    assert any(text == "1. Problem 1" for text in texts)
    assert not any("https://" in text for text in texts)


def test_an_empty_pool_still_gets_no_buttons():
    view = build_guard_view(
        MagicMock(),
        CONFIG,
        model(problems=()),
        output_name="DP-0",
        on_open=lambda _url: None,
    )

    assert view.open_buttons == []
    assert len(view.problem_labels) == 1


# -- break-glass -----------------------------------------------------------


def test_the_breakglass_instructions_are_always_present(tk_mock):
    view = build_guard_view(MagicMock(), CONFIG, model(), output_name="DP-0")

    assert view.breakglass_label is not None
    texts = [str(call.kwargs.get("text", "")) for call in tk_mock.Label.call_args_list]
    assert any(STOP_COMMAND in text for text in texts)


def test_no_repaint_can_hide_the_breakglass_instructions():
    """It is the one instruction that keeps working when the rest of this
    package does not, so nothing may unpack it."""
    view = build_guard_view(MagicMock(), CONFIG, model(), output_name="DP-0")

    apply_viewmodel([view], model(show_escape=True))
    apply_viewmodel([view], model(show_escape=False))

    view.breakglass_label.pack_forget.assert_not_called()
