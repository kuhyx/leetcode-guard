"""The reader of the tutor's signed ``review_due.json`` (contract C4, reader rule).

Three answers, never a bool: cards due, nothing due, cannot check. Every test
signs with the tutor's own library (``_tutor_fixtures.signed``) and a scratch
key; ``TUTOR_DIR`` is redirected by ``_paths_fixture``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _tutor_signed
from leetcode_guard._review_due import DueRead, DueStatus, ReviewWatch, check_due
from leetcode_guard.tests._tutor_fixtures import ALGO, due_row, signed, write_due

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

T = 1_795_538_800_000
"""A moment in Unix milliseconds."""
MOD = (ALGO, "prefix-sums")
OTHER = (ALGO, "stack-queue")
UNKNOWN = DueRead(DueStatus.UNKNOWN)
CLEAR = DueRead(DueStatus.CLEAR)


def _check(key: Path, *targets: tuple[str, str], at_ms: int = T):
    return check_due(targets or (MOD,), at_ms, key_file=key)


def test_cards_due_at_the_moment_are_counted(hmac_key: Path):
    """Count of ``due_ms <= T``: later cards are not due yet."""
    write_due(
        [due_row("prefix-sums", [T - 5, T - 1, T + 1], at=10.0, key_file=hmac_key)]
    )

    assert _check(hmac_key) == DueRead(DueStatus.DUE, 2, MOD)


def test_a_card_due_exactly_now_is_due(hmac_key: Path):
    """The boundary: ``due == T`` counts."""
    write_due([due_row("prefix-sums", [T], at=10.0, key_file=hmac_key)])

    assert _check(hmac_key) == DueRead(DueStatus.DUE, 1, MOD)
    assert _check(hmac_key, at_ms=T - 1) == CLEAR


def test_an_empty_queue_is_nothing_due(hmac_key: Path):
    """``[]`` is an answer, not silence."""
    write_due([due_row("prefix-sums", [], at=10.0, key_file=hmac_key)])

    assert _check(hmac_key) == CLEAR


def test_no_row_for_the_module_is_cannot_check(hmac_key: Path):
    """Deleting a row cannot be told from never written."""
    write_due([due_row("stack-queue", [T - 1], at=10.0, key_file=hmac_key)])

    assert _check(hmac_key) == UNKNOWN


def test_a_forged_row_makes_the_whole_file_cannot_check(hmac_key: Path):
    """Skipping it could hide the row that carries the due cards."""
    forged = due_row("stack-queue", [T - 1], at=10.0, key_file=hmac_key)
    detail = forged["detail"]
    assert isinstance(detail, dict)
    detail["due_ms"] = []
    good = due_row("prefix-sums", [T - 1], at=10.0, key_file=hmac_key)

    write_due([good, forged])
    assert _check(hmac_key) == UNKNOWN
    write_due([forged, good])
    assert _check(hmac_key) == UNKNOWN


def test_an_entry_that_is_not_a_dict_makes_the_whole_file_cannot_check(
    hmac_key: Path,
):
    """A string among the entries is not skipped either."""
    write_due([due_row("prefix-sums", [T - 1], at=10.0, key_file=hmac_key), "x"])

    assert _check(hmac_key) == UNKNOWN


def test_a_file_that_cannot_be_read_is_cannot_check(hmac_key: Path, missing_key: Path):
    """Missing, not JSON, no ``entries`` array, an unreadable key."""
    assert _check(hmac_key) == UNKNOWN
    path = write_due([due_row("prefix-sums", [T - 1], at=10.0, key_file=hmac_key)])
    assert _check(missing_key) == UNKNOWN
    path.write_text("{not json", encoding="utf-8")
    assert _check(hmac_key) == UNKNOWN
    path.write_text(json.dumps({"entries": {}}), encoding="utf-8")
    assert _check(hmac_key) == UNKNOWN
    path.write_text("[]", encoding="utf-8")
    assert _check(hmac_key) == UNKNOWN


def _with_detail(key: Path, **changes: object) -> dict[str, object]:
    """A signed row whose ``detail`` carries values of the wrong type."""
    row = due_row("prefix-sums", [T - 1], at=99.0, key_file=key)
    row.pop("hmac")
    detail = row["detail"]
    assert isinstance(detail, dict)
    row["detail"] = {**detail, **changes}
    return signed(row, key)


def test_verified_rows_of_another_kind_or_a_bad_detail_are_skipped(hmac_key: Path):
    """Skipped, not fatal: they are signed, just not this contract's."""
    other = signed({"kind": "module_state", "entry_id": "s", "detail": {}}, hmac_key)
    bad_kinds = [
        due_row("prefix-sums", [True], at=99.0, key_file=hmac_key),
        due_row("prefix-sums", [T - 1], at=True, key_file=hmac_key),
        due_row("prefix-sums", [1.5], at=99.0, key_file=hmac_key),
        _with_detail(hmac_key, due_ms="soon"),
        _with_detail(hmac_key, at="late"),
    ]
    no_detail = signed({"kind": "review_due", "entry_id": "d", "detail": 3}, hmac_key)
    wrong_type = {
        "kind": "review_due",
        "entry_id": "due:x:y:1",
        "detail": {"subject": ALGO, "module": 5, "due_ms": [], "at": 99.0},
    }
    write_due(
        [
            due_row("prefix-sums", [], at=10.0, key_file=hmac_key),
            other,
            no_detail,
            *bad_kinds,
            signed(wrong_type, hmac_key),
        ]
    )

    assert _check(hmac_key) == CLEAR


def test_the_row_with_the_greatest_at_wins(hmac_key: Path):
    """An older signed row put back later loses, whatever its place in the file."""
    old = due_row("prefix-sums", [T - 1], at=10.0, key_file=hmac_key)
    new = due_row("prefix-sums", [], at=20.0, key_file=hmac_key)

    write_due([new, old])
    assert _check(hmac_key) == CLEAR
    write_due([old, new])
    assert _check(hmac_key) == CLEAR


def test_a_tie_goes_to_the_later_row(hmac_key: Path):
    """Same ``at``: the row later in the file."""
    first = due_row("prefix-sums", [T - 1], at=10.0, key_file=hmac_key)
    second = due_row("prefix-sums", [], at=10.0, key_file=hmac_key)

    write_due([first, second])
    assert _check(hmac_key) == CLEAR
    write_due([second, first])
    assert _check(hmac_key) == DueRead(DueStatus.DUE, 1, MOD)


def test_a_unit_with_several_modules_takes_the_first_one_that_is_due(hmac_key: Path):
    """The target is the first module (in the unit's order) with a card due."""
    write_due(
        [
            due_row("prefix-sums", [], at=10.0, key_file=hmac_key),
            due_row("stack-queue", [T - 1, T - 2], at=10.0, key_file=hmac_key),
        ]
    )

    assert _check(hmac_key, MOD, OTHER) == DueRead(DueStatus.DUE, 2, OTHER)


def test_one_unknown_module_cannot_hide_a_due_one_but_does_hide_a_clear_one(
    hmac_key: Path,
):
    """Due somewhere is due; otherwise any module we cannot see is not "nothing"."""
    write_due([due_row("stack-queue", [T - 1], at=10.0, key_file=hmac_key)])
    assert _check(hmac_key, MOD, OTHER) == DueRead(DueStatus.DUE, 1, OTHER)

    write_due([due_row("stack-queue", [], at=10.0, key_file=hmac_key)])
    assert _check(hmac_key, MOD, OTHER) == UNKNOWN


def test_no_targets_is_cannot_check(hmac_key: Path):
    """A unit that maps no module has nothing to check."""
    assert check_due((), T, key_file=hmac_key) == UNKNOWN


def test_the_reader_itself_logs_nothing(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """The watch writes the one line; the read never fills the log, with the reason kept."""
    with caplog.at_level(logging.DEBUG):
        answer = _check(hmac_key)
    assert answer == UNKNOWN
    assert "review_due.json" in answer.reason
    assert caplog.records == []


def test_the_watch_warns_once_across_many_reads(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """One warning per lock run, with the reason; later ticks stay silent."""
    watch = ReviewWatch(key_file=hmac_key)

    with caplog.at_level(logging.WARNING):
        assert watch.read((MOD,), T) == UNKNOWN
        first = len(caplog.records)
        reads = [watch.read((MOD,), T) for _ in range(4)]
        write_due([due_row("prefix-sums", [T - 1], at=1.0, key_file=hmac_key)])
        due = watch.read((MOD,), T)
        path = _tutor_signed.TUTOR_DIR / "review_due.json"
        path.write_text("junk", encoding="utf-8")
        again = watch.read((MOD,), T)

    assert first >= 1
    assert reads == [UNKNOWN] * 4
    assert due.status is DueStatus.DUE
    assert again == UNKNOWN
    assert len(caplog.records) == first
