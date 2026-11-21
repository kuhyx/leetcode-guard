"""Tests for the harvester's side: submissions and the theory snapshot."""

from __future__ import annotations

import pytest

from leetcode_guard._attempt_model import THEORY_VALUES, day_of
from leetcode_guard._attempt_store import (
    add_beat,
    load,
    merge_submissions,
    snapshot_theory,
)
from leetcode_guard._curriculum import Theory
from leetcode_guard.tests._attempt_helpers import (
    DAY,
    KEY,
    SECONDS_PER_DAY,
    T0,
    attempts_path,
)


def test_new_rows_are_counted_and_stored() -> None:
    """The record is created if the day has no beats yet."""
    rows = [
        ("1", "two-sum", "Wrong Answer", T0),
        ("2", "two-sum", "Accepted", T0 + 30),
        ("3", "add-two-numbers", "Accepted", T0 + 40),
    ]

    assert merge_submissions(rows, now=T0 + 50) == 3

    records = load()
    assert set(records[KEY].submissions) == {"1", "2"}
    assert records[f"{DAY}|add-two-numbers"].submissions["3"].status == "Accepted"


def test_the_same_rows_again_are_idempotent() -> None:
    """Nothing new, nothing written."""
    rows = [("1", "two-sum", "Accepted", T0)]
    merge_submissions(rows, now=T0)
    before = attempts_path().read_bytes()

    assert merge_submissions(rows, now=T0) == 0

    assert attempts_path().read_bytes() == before


def test_a_known_id_keeps_its_first_status() -> None:
    """LeetCode's verdict for an id is final; a replay never rewrites it."""
    merge_submissions([("1", "two-sum", "Accepted", T0)], now=T0)

    assert merge_submissions([("1", "two-sum", "Wrong Answer", T0)], now=T0) == 0

    assert load()[KEY].submissions["1"].status == "Accepted"


def test_a_row_lands_on_the_day_of_its_own_timestamp() -> None:
    """Yesterday's submission does not join today's record."""
    yesterday = T0 - SECONDS_PER_DAY

    merge_submissions([("1", "two-sum", "Accepted", yesterday)], now=T0)

    assert set(load()) == {f"{day_of(yesterday)}|two-sum"}


def test_a_row_older_than_retention_is_not_counted() -> None:
    """It would be pruned at once, so it is skipped without a write."""
    old = T0 - 200 * SECONDS_PER_DAY

    assert merge_submissions([("1", "two-sum", "Accepted", old)], now=T0) == 0

    assert not attempts_path().exists()


def test_no_rows_touch_nothing() -> None:
    """An empty batch takes no lock and writes no file."""
    assert merge_submissions([], now=T0) == 0

    assert not attempts_path().exists()


def test_no_record_means_no_theory_write() -> None:
    """A snapshot never creates a record."""
    assert not snapshot_theory(DAY, "two-sum", "done", now=T0)

    assert not attempts_path().exists()


def test_theory_is_set_once_and_never_overwritten() -> None:
    """The second call, with another value, changes nothing."""
    add_beat("two-sum", "description", now=T0)

    assert snapshot_theory(DAY, "two-sum", "pending", now=T0)
    assert not snapshot_theory(DAY, "two-sum", "done", now=T0)

    assert load()[KEY].theory_at_solve == "pending"


@pytest.mark.parametrize("value", ["none", "done", "pending", "unknown"])
def test_every_curriculum_value_is_accepted(value: str) -> None:
    """The tuple mirrors ``_curriculum.Theory`` as plain strings."""
    add_beat("two-sum", "description", now=T0)

    assert snapshot_theory(DAY, "two-sum", value, now=T0)


def test_the_theory_values_match_the_enum() -> None:
    """Guard against drift without the store importing the enum."""
    assert set(THEORY_VALUES) == {member.value for member in Theory}


def test_an_unknown_theory_value_is_a_caller_bug() -> None:
    """Garbage is refused before anything is written."""
    add_beat("two-sum", "description", now=T0)

    with pytest.raises(ValueError, match="theory"):
        snapshot_theory(DAY, "two-sum", "maybe", now=T0)
