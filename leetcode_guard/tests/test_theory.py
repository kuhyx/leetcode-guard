"""Whether the tutor has taught a unit's theory, read from the tutor's files.

The file shapes below were measured against ``~/.local/share/tutor`` on
2026-11-21; ``scripts/verify_theory_shape.py`` re-checks them live.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._curriculum import Theory, parse_curriculum
from leetcode_guard._theory import unit_theory

if TYPE_CHECKING:
    from pathlib import Path

DOCUMENT = {
    "units": [
        {"id": "scans", "tags": ["array"]},
        {
            "id": "bits",
            "tags": ["bit"],
            "tutor": {"subject": "algo", "modules": ["bits"]},
        },
        {
            "id": "trees",
            "tags": ["tree"],
            "tutor": {"subject": "algo", "modules": ["dfs", "bfs"]},
        },
        {
            "id": "sql",
            "tags": ["database"],
            "tutor": {"subject": "mysql", "modules": ["joins"]},
        },
    ]
}
CARDS = {
    "xor": {"module": "bits", "suspended": False},
    "masks": {"module": "bits", "suspended": False},
    "retired": {"module": "bits", "suspended": True},
    "preorder": {"module": "dfs", "suspended": False},
}


def taught(subject: str, card: str) -> dict[str, object]:
    """One ``taught`` event, shaped like the tutor's own log line."""
    return {"dev": "d", "eid": "e", "k": "taught", "s": subject, "c": card, "at": 1}


def tutor_dir(tmp_path: Path, *events: dict[str, object], cards: object = None) -> Path:
    """A tutor data dir holding subject ``algo`` and the given log events."""
    root = tmp_path / "tutor"
    subject = root / "subjects" / "algo"
    subject.mkdir(parents=True)
    document = CARDS if cards is None else cards
    (subject / "cards.json").write_text(json.dumps(document), encoding="utf-8")
    lines = "".join(json.dumps(event) + "\n" for event in events)
    (root / "log.jsonl").write_text(lines, encoding="utf-8")
    return root


def states(root: Path) -> list[Theory]:
    """Each unit's theory state, read from ``root``."""
    curriculum = parse_curriculum(DOCUMENT)
    assert curriculum is not None
    return list(unit_theory(curriculum, root))


def test_a_module_is_done_once_every_live_card_was_taught(tmp_path: Path):
    """kuhy's rule (2026-11-21): taught once, not "mastered". A suspended card
    can never be taught, so it must not hold the block back."""
    root = tutor_dir(tmp_path, taught("algo", "xor"), taught("algo", "masks"))

    assert states(root)[1] is Theory.DONE


def test_one_untaught_card_keeps_the_module_pending(tmp_path: Path):
    """Half a module is not the theory."""
    root = tutor_dir(tmp_path, taught("algo", "xor"))

    assert states(root)[1] is Theory.PENDING


def test_a_module_with_no_cards_yet_is_pending(tmp_path: Path):
    """The tutor generates cards when a module unlocks; until then (or with a
    mistyped module id) there is nothing taught."""
    root = tutor_dir(tmp_path, taught("algo", "preorder"))

    assert states(root)[2] is Theory.PENDING


def test_every_module_of_a_unit_must_be_done(tmp_path: Path):
    """A unit mapped to two modules waits for both."""
    cards = {**CARDS, "levels": {"module": "bfs", "suspended": False}}
    events = (taught("algo", "preorder"), taught("algo", "levels"))

    assert states(tutor_dir(tmp_path, events[0], cards=cards))[2] is Theory.PENDING
    assert states(tutor_dir(tmp_path / "b", *events, cards=cards))[2] is Theory.DONE


def test_a_card_taught_in_another_subject_does_not_count(tmp_path: Path):
    """Card ids are only unique inside a subject."""
    root = tutor_dir(tmp_path, taught("other", "xor"), taught("algo", "masks"))

    assert states(root)[1] is Theory.PENDING


def test_other_events_are_not_teaching(tmp_path: Path):
    """A review of a card says nothing about it having been taught here."""
    review = {**taught("algo", "xor"), "k": "review"}
    root = tutor_dir(tmp_path, review, taught("algo", "masks"), {"k": "taught"}, [1])

    assert states(root)[1] is Theory.PENDING


def test_a_unit_without_a_tutor_module_has_nothing_to_wait_for(tmp_path: Path):
    """No theory mapped: the block is never marked."""
    assert states(tutor_dir(tmp_path))[0] is Theory.NONE


def test_a_missing_log_is_unknown_not_done(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """Cannot check is not "taught"."""
    root = tutor_dir(tmp_path)
    (root / "log.jsonl").unlink()

    with caplog.at_level(logging.WARNING):
        assert states(root) == [
            Theory.NONE,
            Theory.UNKNOWN,
            Theory.UNKNOWN,
            Theory.UNKNOWN,
        ]

    assert "log.jsonl" in caplog.text


def test_a_missing_subject_is_unknown(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """The subject has not been created in the tutor yet."""
    with caplog.at_level(logging.WARNING):
        assert states(tutor_dir(tmp_path))[3] is Theory.UNKNOWN

    assert "mysql" in caplog.text


@pytest.mark.parametrize(
    "cards",
    [[], {"xor": "bits"}, {"xor": {"module": 3}}, {"xor": {"suspended": False}}],
)
def test_a_cards_file_of_another_shape_is_unknown(
    tmp_path: Path, cards: object, caplog: pytest.LogCaptureFixture
):
    """A tutor schema change must read as "cannot check", loudly."""
    with caplog.at_level(logging.WARNING):
        assert states(tutor_dir(tmp_path, cards=cards))[1] is Theory.UNKNOWN

    assert "cards" in caplog.text


def test_an_unreadable_cards_file_is_unknown(tmp_path: Path):
    """Torn JSON in the cards file."""
    root = tutor_dir(tmp_path)
    (root / "subjects" / "algo" / "cards.json").write_text("{", encoding="utf-8")

    assert states(root)[1] is Theory.UNKNOWN


def test_a_torn_log_line_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The tutor appends while this reads: one half-written line must not hide
    the events around it."""
    root = tutor_dir(tmp_path, taught("algo", "xor"), taught("algo", "masks"))
    with (root / "log.jsonl").open("a", encoding="utf-8") as log:
        log.write('\n{"k": "taught", "s": "al')

    with caplog.at_level(logging.WARNING):
        assert states(root)[1] is Theory.DONE

    assert "torn" in caplog.text


def test_no_tutor_file_is_touched_when_no_unit_maps_a_module(tmp_path: Path):
    """Before the subjects exist the guard must not warn on every run."""
    curriculum = parse_curriculum({"units": [{"id": "scans", "tags": ["array"]}]})
    assert curriculum is not None

    assert unit_theory(curriculum, tmp_path / "absent") == (Theory.NONE,)
