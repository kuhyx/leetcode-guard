"""Tests for reading ``attempts.json``: tolerant, typed, never writing.

Display-only data with two writer processes: the properties worth pinning are
the contract on disk and that a bad file degrades to "no data" with a warning
instead of raising into the status API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from leetcode_guard import _attempt_paths, _constants
from leetcode_guard._attempt_store import (
    add_beat,
    load,
    merge_submissions,
    snapshot_theory,
)
from leetcode_guard.tests._attempt_helpers import (
    DAY,
    KEY,
    T0,
    attempts_path,
    record,
    seed,
)


def test_the_file_is_redirected_into_the_test_data_dir() -> None:
    """The fixture's redirect holds: nothing here touches ``~/.local``."""
    assert attempts_path() == _constants.DATA_DIR / "attempts.json"


def test_the_shipped_name_is_attempts_json() -> None:
    """The on-disk contract fixes the file name."""
    source = Path(_attempt_paths.__file__).read_text(encoding="utf-8")
    assert '"attempts.json"' in source


def test_a_missing_file_is_empty() -> None:
    """No file yet is an ordinary state, not a problem."""
    assert load() == {}


def test_a_roundtrip_gives_typed_records() -> None:
    """What the writers wrote reads back as typed records."""
    add_beat("two-sum", "description", now=T0)
    add_beat("two-sum", "editorial", now=T0 + 60)
    merge_submissions([("77", "two-sum", "Wrong Answer", T0 + 100)], now=T0 + 100)
    assert snapshot_theory(DAY, "two-sum", "done", now=T0 + 100)

    found = load(attempts_path())[KEY]

    assert (found.day, found.slug) == (DAY, "two-sum")
    assert [(beat.at, beat.tab) for beat in found.beats] == [
        (T0, "description"),
        (T0 + 60, "editorial"),
    ]
    assert found.submissions["77"].status == "Wrong Answer"
    assert found.submissions["77"].at == T0 + 100
    assert found.theory_at_solve == "done"


def test_a_garbage_file_is_empty_warned_and_left_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reads never rename: only a writer sets a corrupt file aside."""
    path = attempts_path()
    path.write_text("{nope", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert load() == {}

    assert "attempts" in caplog.text
    assert path.read_text(encoding="utf-8") == "{nope"
    assert not path.with_name("attempts.json.corrupt").exists()


@pytest.mark.parametrize(
    "document",
    [[], {"version": 2, "records": {}}, {"version": 1, "records": []}, {"records": {}}],
)
def test_a_wrong_shape_is_empty_and_warned(
    caplog: pytest.LogCaptureFixture, document: object
) -> None:
    """Top-level shape faults give an empty map and a warning."""
    attempts_path().write_text(json.dumps(document), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert load() == {}

    assert "attempts" in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {**record(DAY), "beats": [[1, 2]]},
        {**record(DAY), "beats": "x"},
        {**record(DAY), "beats": [[True, "description"]]},
        {**record(DAY), "submissions": {"1": {"status": "x"}}},
        {**record(DAY), "submissions": {"1": "x"}},
        {**record(DAY), "submissions": []},
        {**record(DAY), "theory_at_solve": "maybe"},
        record("yesterday"),
        record(DAY, slug="other"),
        record("5"),
        {**record(DAY), "day": 5},
        {**record(DAY), "day": "20261121"},
    ],
)
def test_one_bad_record_is_dropped_and_the_rest_kept(
    caplog: pytest.LogCaptureFixture, bad: object
) -> None:
    """A single malformed record must not hide the good ones."""
    seed(attempts_path(), {KEY: bad, f"{DAY}|valid": record(DAY, "valid")})

    with caplog.at_level(logging.WARNING):
        records = load()

    assert set(records) == {f"{DAY}|valid"}
    assert "attempts" in caplog.text


def test_an_unreadable_file_is_empty_and_warned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A path that cannot be read as text counts as no data, with a warning."""
    attempts_path().mkdir()

    with caplog.at_level(logging.WARNING):
        assert load() == {}

    assert "attempts" in caplog.text
