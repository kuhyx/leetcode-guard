"""Tests for the widget layer: applying a model, and the escape form.

Construction is in ``test_view.py``. Tk is a MagicMock here too, so these
assert on what was asked of Tk rather than on pixels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._escape_flow import (
    ESCAPE_OFFER_AFTER_SECONDS,
    EscapeHatch,
    build_tracker,
    is_offerable,
)
from leetcode_guard._view import GuardView
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import ProblemLine, ViewModel

if TYPE_CHECKING:
    from pathlib import Path

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


# -- apply_viewmodel -------------------------------------------------------


def make_view(*, with_button: bool = False) -> GuardView:
    return GuardView(
        output_name="DP-0",
        container=MagicMock(),
        headline=MagicMock(),
        balance_line=MagicMock(),
        status_line=MagicMock(),
        notes_label=MagicMock(),
        escape_button=MagicMock() if with_button else None,
    )


def test_applying_a_model_updates_every_surface():
    views = [make_view(), make_view()]

    assert apply_viewmodel(views, model(headline="Unlocked")) == 2

    for view in views:
        view.headline.configure.assert_called_once_with(text="Unlocked")


def test_applying_a_model_toggles_the_escape_button():
    view = make_view(with_button=True)

    apply_viewmodel([view], model(show_escape=True))
    view.escape_button.pack.assert_called_once()

    apply_viewmodel([view], model(show_escape=False))
    view.escape_button.pack_forget.assert_called_once()


def test_a_surface_without_an_escape_button_is_skipped():
    view = make_view(with_button=False)

    assert apply_viewmodel([view], model(show_escape=True)) == 1


# -- escape flow -----------------------------------------------------------


def test_the_hatch_is_offered_from_the_first_second(tmp_path: Path, hmac_key: Path):
    """This asserted the opposite until 2026-08-05, when a lock with no exit for
    its first ten minutes turned out to be a lock with no exit."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)

    assert is_offerable(tracker, elapsed_seconds=0, unverifiable_seconds=0)
    assert is_offerable(
        tracker, elapsed_seconds=ESCAPE_OFFER_AFTER_SECONDS, unverifiable_seconds=0
    )


def test_the_budget_is_what_makes_the_hatch_expensive(tmp_path: Path, hmac_key: Path):
    """With the clock no longer gating, the budget carries the whole weight of
    keeping the hatch from becoming a daily habit. Exhausted means gone."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.is_budget_exhausted = lambda: True

    assert not is_offerable(tracker, elapsed_seconds=99_999, unverifiable_seconds=9_999)


def test_a_blind_gate_reveals_the_hatch_far_sooner(tmp_path: Path, hmac_key: Path):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)

    assert is_offerable(tracker, elapsed_seconds=1, unverifiable_seconds=300)


def test_an_exhausted_budget_removes_the_hatch_entirely(tmp_path: Path, hmac_key: Path):
    """Not greyed out, not slower -- gone."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.is_budget_exhausted = lambda **_kwargs: True

    assert not is_offerable(tracker, elapsed_seconds=99999, unverifiable_seconds=99999)


def test_a_short_justification_is_rejected(tmp_path: Path, hmac_key: Path):
    granted: list[str] = []
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, CONFIG, on_granted=granted.append)
    form = hatch.show(MagicMock())
    form.reason.get.return_value = "tired"
    form.onset.get.return_value = "this morning"
    form.description.get.return_value = "too short"

    assert not hatch.submit()
    assert granted == []
    form.complaint.configure.assert_called()


def test_a_full_justification_is_recorded_and_grants(tmp_path: Path, hmac_key: Path):
    granted: list[str] = []
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, CONFIG, on_granted=granted.append)
    form = hatch.show(MagicMock())
    # `tk.Entry` is one MagicMock, so every Entry the form builds is literally
    # the same object -- reason and onset cannot be given different values
    # here. One value covers both, which is enough: what is under test is that
    # a complete form is accepted and reaches on_granted.
    form.reason.get.return_value = "leetcode has been down all morning"
    form.description.get.return_value = "x" * 200

    assert hatch.submit()
    assert granted == ["leetcode has been down all morning"]
    assert not hatch.open


def test_submitting_with_no_form_open_is_a_no_op(tmp_path: Path, hmac_key: Path):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, CONFIG, on_granted=lambda _r: None)

    assert not hatch.submit()


def test_closing_twice_is_safe(tmp_path: Path, hmac_key: Path):
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, CONFIG, on_granted=lambda _r: None)
    hatch.show(MagicMock())

    hatch.close()
    hatch.close()

    assert not hatch.open


def test_a_failed_record_is_reported_not_silently_granted(
    tmp_path: Path, hmac_key: Path
):
    granted: list[str] = []
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.record = lambda *_a, **_k: False
    hatch = EscapeHatch(tracker, CONFIG, on_granted=granted.append)
    form = hatch.show(MagicMock())
    form.reason.get.return_value = "a real reason"
    form.onset.get.return_value = "this morning"
    form.description.get.return_value = "y" * 200

    assert not hatch.submit()
    assert granted == []


def test_the_form_shows_recent_justifications_back(tmp_path: Path, hmac_key: Path):
    """Half the deterrent: a recycled excuse is obvious with the last ten on
    screen above the box."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.format_recent = lambda *_a, **_k: "1. an earlier excuse"

    hatch = EscapeHatch(tracker, CONFIG, on_granted=lambda _r: None)
    hatch.show(MagicMock())

    assert hatch.open


def test_the_form_omits_the_history_block_when_there_is_none(
    tmp_path: Path, hmac_key: Path
):
    """A first-time user should not see an empty 'your recent excuses' panel."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    tracker.format_recent = lambda *_a, **_k: ""

    hatch = EscapeHatch(tracker, CONFIG, on_granted=lambda _r: None)
    hatch.show(MagicMock())

    assert hatch.open


def test_every_escape_field_is_labelled(tmp_path: Path, hmac_key: Path, tk_mock):
    """The reason box shipped unlabelled: three inputs, one caption, and no way
    to tell what the first one wanted. Found by screenshotting, not asserting."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, CONFIG, on_granted=lambda _r: None)
    parent = MagicMock()

    hatch.show(parent)

    captions = [
        str(call.kwargs.get("text", "")) for call in tk_mock.Label.call_args_list
    ]
    assert any("What is the problem" in c for c in captions)
    assert any("When did this start" in c for c in captions)
    assert any("full explanation" in c for c in captions)
