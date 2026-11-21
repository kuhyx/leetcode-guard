"""An ``untaught`` log row takes a card back out of the taught set.

Measured in the tutor's source on 2026-11-21 (``tutor/fold.py:215-233``,
``tutor/source.py:158-174``): un-ticking a card appends
``{"k": "untaught", "s": ..., "c": ...}`` and the tutor's own fold treats the
card as not taught until a later ``taught`` row. Rows apply in file order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._curriculum import Theory
from leetcode_guard.tests.test_theory import states, taught, tutor_dir

if TYPE_CHECKING:
    from pathlib import Path


def untaught(subject: str, card: str) -> dict[str, object]:
    """One ``untaught`` event, shaped like the tutor's own log line."""
    return {"dev": "d", "eid": "e", "k": "untaught", "s": subject, "c": card, "at": 2}


def bits_state(tmp_path: Path, *events: dict[str, object]) -> Theory:
    """The ``bits`` unit's state (live cards ``xor`` and ``masks``)."""
    return states(tutor_dir(tmp_path, *events))[1]


def test_untaught_after_taught_makes_the_unit_pending(tmp_path: Path):
    """The tutor shows the un-ticked card as not taught; so must the guard."""
    events = (taught("algo", "xor"), taught("algo", "masks"), untaught("algo", "xor"))

    assert bits_state(tmp_path, *events) is Theory.PENDING


def test_taught_again_after_untaught_counts(tmp_path: Path):
    """Last row wins, in file order."""
    events = (
        taught("algo", "xor"),
        taught("algo", "masks"),
        untaught("algo", "xor"),
        taught("algo", "xor"),
    )

    assert bits_state(tmp_path, *events) is Theory.DONE


def test_untaught_with_no_earlier_taught_is_harmless(tmp_path: Path):
    """The card was never taught: nothing to remove, nothing raised."""
    events = (untaught("algo", "xor"), taught("algo", "masks"))

    assert bits_state(tmp_path, *events) is Theory.PENDING


def test_untaught_before_taught_leaves_it_taught(tmp_path: Path):
    """File order, not event kind, decides."""
    events = (untaught("algo", "xor"), taught("algo", "xor"), taught("algo", "masks"))

    assert bits_state(tmp_path, *events) is Theory.DONE


def test_untaught_of_another_subject_or_card_changes_nothing(tmp_path: Path):
    """Only the exact (subject, card) pair is taken back."""
    events = (
        taught("algo", "xor"),
        taught("algo", "masks"),
        untaught("mysql", "xor"),
        untaught("algo", "no-such-card"),
    )

    assert bits_state(tmp_path, *events) is Theory.DONE


def test_an_untaught_row_without_string_keys_is_ignored(tmp_path: Path):
    """A malformed row is not evidence of anything."""
    events = (
        taught("algo", "xor"),
        taught("algo", "masks"),
        {"k": "untaught", "s": "algo"},
        {"k": "untaught", "s": 7, "c": "xor"},
    )

    assert bits_state(tmp_path, *events) is Theory.DONE
