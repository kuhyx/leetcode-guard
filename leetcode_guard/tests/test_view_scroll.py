"""Tests for the scrolling suggestion list.

Tk is a MagicMock (``conftest._block_real_tk``). The wheel reaching the widgets
under a real grab is checked on Xvfb by hand; here the contract is what the
viewport asks of Tk and when the list grows.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from gatelock import LockConfig
import pytest

from leetcode_guard._view import GuardView, build_guard_view
from leetcode_guard._view_problems import INITIAL_ROWS, ROW_BATCH, append_rows
from leetcode_guard._view_scroll import ScrollArea, grow_rows
from leetcode_guard._viewmodel import ProblemLine, ViewModel

CONFIG = LockConfig()


def lines(count: int) -> tuple[ProblemLine, ...]:
    return tuple(
        ProblemLine(label=f"{i + 1}. P{i}", url=f"https://x/{i}", slug=f"p{i}")
        for i in range(count)
    )


def model(count: int) -> ViewModel:
    return ViewModel(
        headline="h",
        balance_line="b",
        status_line="s",
        notes=(),
        problems=lines(count),
        unlocked=False,
        show_escape=False,
    )


def _bound(widget: MagicMock, sequence: str) -> Any:
    for call in widget.bind.call_args_list:
        if call.args[0] == sequence:
            return call.args[1]
    msg = f"{sequence} not bound"
    raise AssertionError(msg)


def test_the_list_builds_two_screens_not_the_whole_pool() -> None:
    view = build_guard_view(MagicMock(), CONFIG, model(500), output_name="DP-0")

    assert len(view.problem_labels) == INITIAL_ROWS
    assert len(view.lines) == 500


def test_scrolling_near_the_end_builds_the_next_batch_and_reports_it() -> None:
    revealed: list[int] = []
    view = build_guard_view(
        MagicMock(),
        CONFIG,
        model(500),
        output_name="DP-0",
        on_open=lambda _u: None,
        on_reveal=revealed.append,
    )

    added = grow_rows(view, CONFIG)

    assert added == ROW_BATCH
    assert len(view.open_buttons) == INITIAL_ROWS + ROW_BATCH
    assert revealed == [INITIAL_ROWS + ROW_BATCH]


def test_a_fully_built_list_does_not_grow() -> None:
    view = build_guard_view(MagicMock(), CONFIG, model(3), output_name="DP-0")

    assert grow_rows(view, CONFIG) == 0


def test_growing_without_a_reveal_callback_is_fine() -> None:
    view = GuardView("DP-0", *(MagicMock() for _ in range(5)))
    view.scroll = MagicMock()
    view.lines = lines(4)

    assert grow_rows(view, CONFIG) == 4


@pytest.mark.usefixtures("_block_real_tk")
def test_the_wheel_scrolls_both_ways() -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)
    canvas = area.canvas

    _bound(canvas, "<Button-4>")(None)
    _bound(canvas, "<Button-5>")(None)
    _bound(canvas, "<MouseWheel>")(MagicMock(delta=120))
    _bound(canvas, "<MouseWheel>")(MagicMock(delta=-120))

    units = [c.args[0] for c in canvas.yview_scroll.call_args_list]
    assert units == [-2, 2, -2, 2]


@pytest.mark.usefixtures("_block_real_tk")
def test_reaching_the_end_grows_once_per_idle_pass() -> None:
    grown: list[int] = []
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: grown.append(1))

    area._on_view_moved("0.0", "0.5")
    assert not area.canvas.after_idle.called
    area._on_view_moved("0.5", "0.9")
    area._on_view_moved("0.5", "0.95")

    assert area.canvas.after_idle.call_count == 1
    area.canvas.after_idle.call_args.args[0]()
    assert grown == [1]


@pytest.mark.usefixtures("_block_real_tk")
def test_the_scrollbar_drives_the_canvas() -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)

    area._on_scrollbar("moveto", "0.5")

    area.canvas.yview.assert_called_with("moveto", "0.5")


@pytest.mark.parametrize(("current", "widened"), [(0, True), (5000, False)])
@pytest.mark.usefixtures("_block_real_tk")
def test_the_viewport_widens_but_never_narrows(*, current: int, widened: bool) -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)
    area.canvas.cget.return_value = current
    area.canvas.configure.reset_mock()

    area._on_inner_resized(None)

    widths = [c.kwargs.get("width") for c in area.canvas.configure.call_args_list]
    assert (900 in widths) is widened


@pytest.mark.usefixtures("_block_real_tk")
def test_the_inner_frame_tracks_the_canvas_width() -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)

    area._on_canvas_resized(MagicMock(width=640))

    area.canvas.itemconfigure.assert_called_with(area._window, width=640)


@pytest.mark.usefixtures("_block_real_tk")
def test_the_viewport_is_as_tall_as_the_visible_share() -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)

    area.fit_rows(16, 8)

    area.canvas.configure.assert_any_call(height=200)
    area.scrollbar.pack.assert_called_once()


@pytest.mark.usefixtures("_block_real_tk")
def test_a_short_list_has_no_scrollbar() -> None:
    area = ScrollArea(MagicMock(), CONFIG, on_near_end=lambda: None)

    area.fit_rows(3, 8)

    area.canvas.configure.assert_any_call(height=400)
    area.scrollbar.pack_forget.assert_called_once()


def test_rows_without_a_wheel_binder_still_build() -> None:
    labels, buttons = append_rows(MagicMock(), CONFIG, lines(2), None)

    assert len(labels) == 2
    assert buttons == []
