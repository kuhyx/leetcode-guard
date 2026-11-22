"""The THEORY card and the SOLVE bar on a surface, and phase changes mid-lock."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from leetcode_guard import _glyphs as g
from leetcode_guard._view import build_guard_view
from leetcode_guard._view_phase import mark_learn_unavailable, paint_phase
from leetcode_guard._view_types import PhaseWidgets, UnitBar, ViewHooks
from leetcode_guard._viewmodel_phase import NONE_SCREEN, build_phase_screen
from leetcode_guard.tests._phase_fixtures import NEXT, SOLVE, SUBJECT, THEORY, phase
from leetcode_guard.tests._view_fixtures import CONFIG, mock_view, model

ROUTE = f"/learn/{SUBJECT}/prefix-sums"


def _widgets() -> PhaseWidgets:
    """A phase slot whose every widget is its own mock."""
    return PhaseWidgets(
        slot=MagicMock(),
        card=MagicMock(),
        title=MagicMock(),
        ready_mark=MagicMock(),
        progress=MagicMock(),
        counts=MagicMock(),
        rate=MagicMock(),
        learn=MagicMock(),
        unit_bar=UnitBar(frame=MagicMock(), label=MagicMock()),
    )


def _learn_command(widgets: PhaseWidgets):
    return widgets.learn.configure.call_args.kwargs["command"]


def test_a_theory_surface_leads_with_the_card_and_a_large_learn_button(tk_mock):
    """The learn button is built in the display font, above Open's size."""
    pressed: list[str] = []
    build_guard_view(
        MagicMock(),
        CONFIG,
        model(screen=build_phase_screen(THEORY)),
        output_name="DP-0",
        hooks=ViewHooks(on_open=lambda _u: None, on_learn=pressed.append),
    )
    buttons = {
        call.kwargs.get("text"): call.kwargs for call in tk_mock.Button.call_args_list
    }

    assert abs(buttons[g.LEARN]["font"][1]) > abs(buttons[g.OPEN]["font"][1])
    configured = tk_mock.Button.return_value.configure.call_args_list
    learn = next(c for c in configured if c.kwargs.get("text") == g.LEARN)
    learn.kwargs["command"]()
    assert pressed == [ROUTE]
    texts = [
        c.kwargs.get("text") for c in tk_mock.Label.return_value.configure.mock_calls
    ]
    assert f"{g.THEORY_PENDING}  prefix-sums" in texts
    assert "3 / 12" in texts


def test_theory_shows_the_card_and_hides_the_bar():
    """Card packed, bar forgotten, texts and the bar fill from the model."""
    widgets = _widgets()
    paint_phase(widgets, CONFIG, build_phase_screen(THEORY), lambda _r: None)

    widgets.card.pack.assert_called_once()
    widgets.unit_bar.frame.pack_forget.assert_called_once()
    widgets.counts.configure.assert_called_with(text="3 / 12")
    rectangle = widgets.progress.create_rectangle.call_args.args
    assert rectangle[2] == round(CONFIG.space("xl") * 12 * 3 / 12)
    widgets.learn.pack.assert_called_once()


def test_solve_shows_the_bar_and_no_theory_control():
    """SOLVE: the card (and with it the learn button) is off the screen."""
    widgets = _widgets()
    paint_phase(widgets, CONFIG, build_phase_screen(SOLVE), lambda _r: None)

    widgets.card.pack_forget.assert_called_once()
    widgets.card.pack.assert_not_called()
    widgets.unit_bar.label.configure.assert_called_once_with(text="prefix-sums  1 / 3")
    widgets.unit_bar.frame.pack.assert_called_once()
    widgets.learn.configure.assert_not_called()


def test_none_shows_neither():
    """Every unit finished: today's list, nothing above it."""
    widgets = _widgets()
    paint_phase(widgets, CONFIG, NONE_SCREEN, None)

    widgets.card.pack_forget.assert_called_once()
    widgets.unit_bar.frame.pack_forget.assert_called_once()
    widgets.unit_bar.frame.pack.assert_not_called()


def test_unknown_counts_draw_an_empty_track_and_no_route_hides_the_button():
    """``cards_*`` None never fills the bar; no target means no button."""
    widgets = _widgets()
    screen = build_phase_screen(phase(cards_taught=None, learn_target=None))
    paint_phase(widgets, CONFIG, screen, lambda _r: None)

    widgets.progress.delete.assert_called_once_with("all")
    widgets.progress.create_rectangle.assert_not_called()
    widgets.learn.pack_forget.assert_called_once()
    widgets.learn.configure.assert_not_called()


def test_without_a_handler_the_button_is_inert():
    """The fit harness renders with no hooks: an empty command, never a crash."""
    widgets = _widgets()
    paint_phase(widgets, CONFIG, build_phase_screen(THEORY), None)

    assert _learn_command(widgets) == ""


def test_not_ready_lessons_show_the_mark_and_the_plan_button():
    """Not ready: the dotted circle on the card, the plan glyph on the button."""
    widgets = _widgets()
    pressed: list[str] = []
    paint_phase(
        widgets, CONFIG, build_phase_screen(phase(lessons_ready=False)), pressed.append
    )
    _learn_command(widgets)()

    widgets.ready_mark.configure.assert_called_with(text=g.NOT_READY)
    assert widgets.learn.configure.call_args.kwargs["text"] == g.PLAN
    assert pressed == [f"/plan/{SUBJECT}"]


def test_a_hand_over_rebinds_learn_to_the_next_unit():
    """THEORY(u) -> SOLVE(u) -> THEORY(next): the button opens next, not u."""
    widgets = _widgets()
    pressed: list[str] = []
    for view in (THEORY, SOLVE, NEXT):
        paint_phase(widgets, CONFIG, build_phase_screen(view), pressed.append)
    _learn_command(widgets)()

    assert pressed == [f"/learn/{SUBJECT}/stack-queue"]
    assert widgets.card.pack.call_count == 2
    assert widgets.unit_bar.frame.pack.call_count == 1


def test_a_cannot_open_mark_survives_the_next_repaint_of_the_same_screen():
    """The no-entry mark stays until the screen moves on."""
    widgets = _widgets()
    view = mock_view(phase=widgets)
    screen = build_phase_screen(THEORY)
    paint_phase(widgets, CONFIG, screen, None)

    assert mark_learn_unavailable([view, mock_view()], CONFIG) == 1
    widgets.learn.configure.assert_called_with(
        text=g.NO_ENTRY, bg=CONFIG.palette.danger
    )
    calls = widgets.learn.configure.call_count
    paint_phase(widgets, CONFIG, replace(screen), None)
    assert widgets.learn.configure.call_count == calls
    paint_phase(widgets, CONFIG, build_phase_screen(NEXT), None)
    assert widgets.learn.configure.call_args.kwargs["text"] == g.LEARN
