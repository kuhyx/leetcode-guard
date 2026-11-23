"""Tests for heartbeats: dedupe, local days and the 180-day retention."""

from __future__ import annotations

from datetime import date, timedelta
import json
import time
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._attempt_model import day_of
from leetcode_guard._attempt_store import Outcome, add_beat, load
from leetcode_guard.tests._attempt_helpers import (
    DAY,
    KEY,
    SECONDS_PER_DAY,
    T0,
    attempts_path,
    raw,
    record,
    seed,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="kiritimati")
def fixture_kiritimati(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Local time UTC+14, restored afterwards (``tzset`` is process-wide)."""
    with monkeypatch.context() as local:  # its own undo: the path isolation stays
        local.setenv("TZ", "Pacific/Kiritimati")
        time.tzset()
        yield
    time.tzset()


def test_the_first_beat_creates_the_record() -> None:
    """The record carries the contract's fields."""
    assert add_beat("two-sum", "description", now=T0) is Outcome.WRITTEN

    assert raw(attempts_path()) == {
        "version": 1,
        "records": {
            KEY: {
                "day": DAY,
                "slug": "two-sum",
                "beats": [[T0, "description"]],
                "submissions": {},
            },
        },
    }


def test_the_timestamp_is_whole_seconds_of_the_server_clock() -> None:
    """A float clock is stored as an int."""
    add_beat("two-sum", "description", now=T0 + 0.9)

    assert load()[KEY].beats[0].at == T0


def test_a_same_tab_beat_under_ten_seconds_is_skipped() -> None:
    """No write at all: the file is byte-identical."""
    path = attempts_path()
    add_beat("two-sum", "description", now=T0)
    before = path.read_bytes()

    assert add_beat("two-sum", "description", now=T0 + 9) is Outcome.SKIPPED

    assert path.read_bytes() == before


def test_a_same_tab_beat_at_ten_seconds_is_kept() -> None:
    """The skip window is strictly under ten seconds."""
    add_beat("two-sum", "description", now=T0)

    assert add_beat("two-sum", "description", now=T0 + 10) is Outcome.WRITTEN

    assert [beat.at for beat in load()[KEY].beats] == [T0, T0 + 10]


def test_another_tab_is_never_a_duplicate() -> None:
    """Switching tabs inside ten seconds is real signal."""
    add_beat("two-sum", "description", now=T0)

    assert add_beat("two-sum", "editorial", now=T0 + 1) is Outcome.WRITTEN


def test_a_clock_that_moved_back_keeps_beats_ascending() -> None:
    """A step back is clamped to the previous beat."""
    add_beat("two-sum", "description", now=T0)

    assert add_beat("two-sum", "editorial", now=T0 - 500) is Outcome.WRITTEN

    assert [beat.at for beat in load()[KEY].beats] == [T0, T0]


def test_each_day_and_slug_gets_its_own_record() -> None:
    """The key is ``<local day>|<slug>``."""
    later = T0 + 2 * SECONDS_PER_DAY
    add_beat("two-sum", "description", now=T0)
    add_beat("two-sum", "description", now=later)
    add_beat("add-two-numbers", "description", now=T0)

    assert set(load()) == {KEY, f"{day_of(later)}|two-sum", f"{DAY}|add-two-numbers"}


@pytest.mark.usefixtures("kiritimati")
def test_the_day_is_local_not_utc() -> None:
    """10:00 UTC is already the next calendar day at UTC+14."""
    ten_utc = 1_767_261_600  # 2026-01-01 10:00:00 UTC
    assert day_of(ten_utc - 1) == "2026-01-01"
    assert day_of(ten_utc) == "2026-01-02"


def test_the_boundary_is_one_hundred_eighty_days() -> None:
    """Day 180 stays, day 181 goes."""
    today = date.fromisoformat(DAY)
    keep = (today - timedelta(days=180)).isoformat()
    drop = (today - timedelta(days=181)).isoformat()
    seed(
        attempts_path(),
        {f"{keep}|a": record(keep, "a"), f"{drop}|b": record(drop, "b")},
    )

    add_beat("two-sum", "description", now=T0)

    assert set(load()) == {f"{keep}|a", KEY}


def test_a_skipped_write_does_not_prune() -> None:
    """Pruning rides on writes; a duplicate beat writes nothing."""
    path = attempts_path()
    add_beat("two-sum", "description", now=T0)
    data = raw(path)
    data["records"]["1999-01-01|old"] = record("1999-01-01", "old")
    path.write_text(json.dumps(data), encoding="utf-8")

    assert add_beat("two-sum", "description", now=T0 + 1) is Outcome.SKIPPED

    assert "1999-01-01|old" in raw(path)["records"]
