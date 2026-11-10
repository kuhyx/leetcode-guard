"""The escape form without words: dots, a live counter, an outlined field.

Tk is the suite's MagicMock, so every ``tk.Entry`` is the same object; the
form's fields are swapped for distinct mocks where the test needs to tell
them apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import EscapeDraft, LockConfig

from leetcode_guard import _glyphs as g
from leetcode_guard._escape_flow import build_tracker
from leetcode_guard._escape_form import (
    EscapeForm,
    budget_marks,
    build_escape_form,
    flag_refusal,
    recent_lines,
)

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = LockConfig()


def _form() -> EscapeForm:
    return EscapeForm(
        frame=MagicMock(),
        reason=MagicMock(name="reason"),
        onset=MagicMock(name="onset"),
        description=MagicMock(name="description"),
        complaint=MagicMock(),
        submit=MagicMock(),
    )


def _draft(reason: str = "r", onset: str = "o", description: str = "") -> EscapeDraft:
    return EscapeDraft(reason=reason, onset=onset, severity=1, description=description)


def _outline(widget: MagicMock) -> int:
    return widget.configure.call_args.kwargs["highlightthickness"]


def test_a_blank_reason_outlines_the_reason_field():
    form = _form()

    flag_refusal(form, _draft(reason=""), CONFIG)

    assert form.flagged is form.reason
    assert _outline(form.reason) > 0
    form.complaint.configure.assert_called_with(text=g.BLIND)


def test_a_blank_onset_outlines_the_onset_field_and_clears_the_last_outline():
    form = _form()
    flag_refusal(form, _draft(reason=""), CONFIG)

    flag_refusal(form, _draft(onset=""), CONFIG)

    assert form.flagged is form.onset
    assert _outline(form.reason) == 0
    assert _outline(form.onset) > 0


def test_a_short_explanation_outlines_the_explanation():
    form = _form()

    flag_refusal(form, _draft(), CONFIG)
    flag_refusal(form, _draft(), CONFIG)

    assert form.flagged is form.description
    assert _outline(form.description) > 0


def test_the_counter_turns_green_at_the_minimum(tk_mock, tmp_path: Path, hmac_key):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    form = build_escape_form(MagicMock(), CONFIG, tracker, lambda: False)
    count = tk_mock.Text.return_value.bind.call_args.args[1]
    minimum = tracker.policy.justification_min_chars

    form.description.get.return_value = "x" * 3
    count()
    short = form.counter.configure.call_args.kwargs
    form.description.get.return_value = "x" * minimum
    count(None)
    enough = form.counter.configure.call_args.kwargs

    assert short == {"text": f"3/{minimum}", "fg": CONFIG.palette.danger}
    assert enough == {"text": f"{minimum}/{minimum}", "fg": CONFIG.palette.success}


def test_past_justifications_are_read_back_as_written(tmp_path: Path, hmac_key):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    assert recent_lines(tracker) == ""
    tracker.record(_draft(reason="flu", description="fever all night"))

    assert "flu: fever all night" in recent_lines(tracker)


def test_the_form_paints_the_read_back(tk_mock, tmp_path: Path, hmac_key):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.record(_draft(reason="flu", description="fever all night"))

    build_escape_form(MagicMock(), CONFIG, tracker, lambda: False)

    texts = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("flu: fever all night" in text for text in texts)


def test_the_budget_is_dots_per_window_or_a_count_past_the_cap(
    tmp_path: Path, hmac_key
):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.record(_draft(description="d"))

    marks = budget_marks(tracker)

    assert marks.startswith(g.ESCAPE)
    assert "●" in marks
    assert "/" in marks.rsplit(g.SEP, 1)[1]


def test_many_owed_solves_collapse_into_a_count():
    assert g.dots(0) == ""
    assert g.dots(3) == g.OWED * 3
    assert g.dots(g.DOT_CAP + 4) == f"{g.OWED}{g.TIMES}{g.DOT_CAP + 4}"
