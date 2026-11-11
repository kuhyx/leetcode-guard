"""Difficulty weights: Easy 1, Medium 2, Hard 4 -- from a signed cache.

The weight of a credit is derived at read time from a per-slug difficulty row
the guard signed itself. An unsigned or edited row must never raise a weight:
editing "Easy" to "Hard" would otherwise quadruple every credit.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _constants, _difficulty
from leetcode_guard._difficulty import credited_slugs, load_weights
from leetcode_guard._ledger_entries import credit_entry, seen_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._progress import DIFFICULTY_WEIGHTS
from leetcode_guard.tests._difficulty_fixtures import write_rows
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, submission

if TYPE_CHECKING:
    from pathlib import Path


def test_the_weights_are_one_two_four():
    """Easy, Medium and Hard weigh 1, 2 and 4."""
    assert DIFFICULTY_WEIGHTS == {"Easy": 1, "Medium": 2, "Hard": 4}


@pytest.mark.usefixtures("data_dir")
def test_signed_rows_set_the_weight(hmac_key: Path):
    """Signed difficulty rows give each slug its difficulty's weight."""
    write_rows(
        _constants.DIFFICULTY_FILE,
        hmac_key,
        {"a": "Easy", "b": "Medium", "c": "Hard"},
    )

    table = load_weights(key_file=hmac_key)

    assert [table.weight(slug) for slug in "abc"] == [1, 2, 4]
    assert table.unknown == set()


@pytest.mark.usefixtures("data_dir")
def test_an_unknown_slug_is_easy_and_logged_once(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Unknown slugs weigh 1 and produce a single warning with their count."""
    table = load_weights(key_file=hmac_key)

    assert table.weight("never-seen") == 1
    assert table.weight("never-seen-2") == 1
    with caplog.at_level(logging.WARNING):
        table.warn_unknown()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "2" in warnings[0].getMessage()


@pytest.mark.usefixtures("data_dir")
def test_nothing_unknown_logs_nothing(hmac_key: Path, caplog: pytest.LogCaptureFixture):
    """With no unknown slugs, warn_unknown logs nothing."""
    table = load_weights(key_file=hmac_key)
    with caplog.at_level(logging.WARNING):
        table.warn_unknown()
    assert not caplog.records


@pytest.mark.usefixtures("data_dir")
def test_an_edited_row_is_ignored(hmac_key: Path):
    """Easy -> Hard by hand must not quadruple a credit."""
    path = _constants.DIFFICULTY_FILE
    write_rows(path, hmac_key, {"a": "Easy"})
    path.write_text(path.read_text().replace("Easy", "Hard"), encoding="utf-8")

    table = load_weights(key_file=hmac_key)

    assert table.weight("a") == 1
    assert table.unknown == {"a"}


@pytest.mark.usefixtures("data_dir")
def test_an_unrecognised_difficulty_is_unknown(hmac_key: Path):
    """A signed row with an unknown difficulty weighs 1 and is marked unknown."""
    write_rows(_constants.DIFFICULTY_FILE, hmac_key, {"a": "Impossible"})

    table = load_weights(key_file=hmac_key)

    assert table.weight("a") == 1
    assert table.unknown == {"a"}


@pytest.mark.usefixtures("data_dir")
def test_an_unreadable_key_trusts_this_devices_rows(hmac_key: Path, tmp_path: Path):
    """Without a readable key, rows this device wrote still set the weight."""
    write_rows(_constants.DIFFICULTY_FILE, hmac_key, {"a": "Hard"})

    table = load_weights(key_file=tmp_path / "no-such-key")

    assert table.weight("a") == 4


def test_the_difficulty_module_never_reads_the_pool_on_the_weight_path():
    """``load_weights`` must not consult the unsigned pool cache."""
    assert "POOL_CACHE_FILE" not in inspect.getsource(_difficulty.load_weights)


def test_credited_slugs_are_sorted_and_skip_markers(hmac_key: Path):
    """credited_slugs lists credited slugs sorted and leaves out seen markers."""
    ledger = Ledger()
    append(
        ledger,
        [
            credit_entry(submission("1", "b"), day=MONDAY, now=NOW, key_file=hmac_key),
            credit_entry(submission("2", "a"), day=MONDAY, now=NOW, key_file=hmac_key),
            seen_entry(submission("3", "z"), day=MONDAY, now=NOW, key_file=hmac_key),
        ],
    )

    assert credited_slugs(ledger) == ["a", "b"]
