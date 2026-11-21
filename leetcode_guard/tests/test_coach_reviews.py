"""The finished-review reader: which slugs the coach's ``review`` events clear."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_guard import _coach_log, _coach_reviews

if TYPE_CHECKING:
    from pathlib import Path


def _write(folder: Path, name: str, *events: object) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def _review(cause: object, **extra: object) -> dict[str, Any]:
    return {
        "event": "review",
        "ts": "2026-11-21T20:00:00+01:00",
        "cause": cause,
        **extra,
    }


def test_the_default_folder_is_redirected_in_tests(tmp_path: Path) -> None:
    """The autouse fixture keeps every test off the real coach log."""
    assert _coach_reviews.COACH_SESSIONS_DIR.is_relative_to(tmp_path)


def test_its_event_names_are_the_ones_the_session_reader_accepts() -> None:
    """The copies of the two names stay tied to ``_coach_log.EVENTS``."""
    assert {_coach_reviews.REVIEW, _coach_reviews.SKELETON} <= _coach_log.EVENTS


@pytest.mark.parametrize("cause", sorted(_coach_reviews.CAUSES))
def test_a_review_with_a_named_cause_clears_its_slug(
    tmp_path: Path, cause: str
) -> None:
    """Every one of the five causes clears; the slug comes from the file name."""
    _write(tmp_path, "2026-11-21-two-sum", {"event": "req"}, _review(cause))

    assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset({"two-sum"})


def test_the_five_causes_are_the_contract() -> None:
    """The closed list the coach writes (coach 0.1.6)."""
    assert (
        frozenset(
            {"statement", "missing-idea", "idea-to-code", "debugging", "interruption"}
        )
        == _coach_reviews.CAUSES
    )


def test_a_missing_idea_review_clears_with_or_without_its_module(
    tmp_path: Path,
) -> None:
    """``module`` is optional payload; it never decides whether a review counts."""
    _write(tmp_path, "2026-11-20-a", _review("missing-idea", module="bit-tricks"))
    _write(tmp_path, "2026-11-20-b", _review("missing-idea"))

    assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset({"a", "b"})


@pytest.mark.parametrize(
    "event",
    [
        {"event": "review"},
        _review(None),
        _review(""),
        _review("laziness"),
        _review(["statement"]),
        _review({"cause": "statement"}),
        {"event": ["review"], "cause": "statement"},
        {"event": "postmortem", "cause": "statement"},
        {"event": "skeleton", "unit": "bit-tricks"},
        ["review", "statement"],
        "review",
    ],
)
def test_anything_but_a_finished_review_clears_nothing(
    tmp_path: Path, event: object
) -> None:
    """A missing, unknown or mistyped cause is not a finished review."""
    _write(tmp_path, "2026-11-21-two-sum", event)

    assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset()


def test_an_undated_file_name_is_its_own_slug(tmp_path: Path) -> None:
    """The coach's naming rule, as ``_coach_log`` reads it."""
    _write(tmp_path, "scratch", _review("debugging"))
    _write(tmp_path, "2026-13-40-odd", _review("debugging"))

    assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset(
        {"scratch", "2026-13-40-odd"}
    )


def test_a_torn_line_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The next well-formed review in the same file still counts."""
    path = _write(tmp_path, "2026-11-21-two-sum")
    path.write_text(
        '{"event": "rev\n\n' + json.dumps(_review("statement")) + "\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset({"two-sum"})

    assert "not JSON" in caplog.text


def test_an_unreadable_file_clears_nothing_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Its slug stays flagged; the other files are still read."""
    (tmp_path / "2026-11-21-bad.jsonl").write_bytes(b"\xff\xfe\n")
    _write(tmp_path, "2026-11-21-good", _review("interruption"))

    with caplog.at_level(logging.WARNING):
        assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset({"good"})

    assert "unreadable" in caplog.text


def test_a_missing_folder_is_no_reviews_yet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing reviewed is a known state, not a failure: no warning."""
    with caplog.at_level(logging.WARNING):
        assert _coach_reviews.reviewed_slugs(tmp_path / "absent") == frozenset()

    assert not caplog.records


def test_an_unlistable_folder_is_could_not_check(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file where the folder should be: warning, nothing cleared, no raise."""
    blocker = tmp_path / "sessions"
    blocker.write_text("not a folder", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert _coach_reviews.reviewed_slugs(blocker) == frozenset()

    assert "could not check" in caplog.text


def test_without_an_argument_it_reads_the_configured_folder() -> None:
    """Read at call time, so the redirect above is the folder it lists."""
    _write(_coach_reviews.COACH_SESSIONS_DIR, "2026-11-21-x", _review("statement"))

    assert _coach_reviews.reviewed_slugs() == frozenset({"x"})


def test_only_jsonl_files_are_session_logs(tmp_path: Path) -> None:
    """A stray file of another kind is not read."""
    (tmp_path / "2026-11-21-y.txt").write_text(
        json.dumps(_review("statement")), encoding="utf-8"
    )

    assert _coach_reviews.reviewed_slugs(tmp_path) == frozenset()
