"""Review first, hardened: a planted file and a raising read fail OPEN.

Each test is one failure the red-team found in the first cut of the rule: the
SOLVE rows show, the lock arms, the poll repaints, one warning per run.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _tutor_signed
from leetcode_guard._review_due import DueRead, DueStatus, ReviewWatch, check_due
from leetcode_guard.tests._guard_factories import probe_of
from leetcode_guard.tests._phase_fixtures import PREFIX
from leetcode_guard.tests._review_first_fixtures import (
    T_MS,
    TARGET,
    install_tutor,
    slugs_of,
)
from leetcode_guard.tests._review_first_fixtures import (
    review_guard as _guard,
)
from leetcode_guard.tests._tutor_fixtures import due_row

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="tutor", autouse=True)
def _tutor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_tutor(monkeypatch)


def _plant(document: object) -> None:
    """``review_due.json`` as anyone with write access to the tutor dir can plant it."""
    path = _tutor_signed.TUTOR_DIR / "review_due.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _entry(**fields: object) -> dict[str, object]:
    return {"kind": "review_due", "entry_id": "x", **fields}


PLANTED = [
    pytest.param(_entry(hmac="é"), id="non-ascii-hmac"),
    pytest.param(_entry(hmac="\ud800"), id="lone-surrogate-hmac"),
    pytest.param(_entry(hmac=7), id="int-hmac"),
    pytest.param(_entry(hmac=[1]), id="list-hmac"),
    pytest.param(_entry(hmac=None), id="null-hmac"),
    pytest.param(_entry(hmac="é", detail="soon"), id="wrong-type-detail"),
    pytest.param(_entry(hmac="é", detail=[3]), id="list-detail"),
    pytest.param(["é"], id="entry-is-a-list"),
    pytest.param(None, id="entry-is-null"),
]


@pytest.mark.parametrize("entry", PLANTED)
def test_a_planted_entry_is_cannot_check_and_never_raises(entry, hmac_key: Path):
    """An entry whose verification fails OR raises makes the whole file unknown."""
    _plant({"version": 1, "entries": [entry]})

    assert check_due((TARGET,), T_MS, key_file=hmac_key).status is DueStatus.UNKNOWN


def test_a_planted_entry_cannot_hide_a_due_card_by_raising(hmac_key: Path):
    """A good due row beside the planted one: still cannot check, not a crash."""
    good = due_row("prefix-sums", [T_MS - 1], at=10.0, key_file=hmac_key)
    _plant({"version": 1, "entries": [good, _entry(hmac="é")]})

    assert check_due((TARGET,), T_MS, key_file=hmac_key).status is DueStatus.UNKNOWN


def test_the_non_strict_read_drops_a_raising_entry_with_a_warning(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """The shared filter: every ``signed_rows`` caller gets the same answer."""
    good = due_row("prefix-sums", [T_MS - 1], at=10.0, key_file=hmac_key)
    _plant({"version": 1, "entries": [good, _entry(hmac="é")]})

    with caplog.at_level(logging.WARNING):
        rows = _tutor_signed.signed_rows("review_due.json", key_file=hmac_key)

    assert rows == [good]
    assert [r for r in caplog.records if "unverified" in r.getMessage()]


def test_the_planted_file_still_arms_the_lock_with_the_solve_rows(
    tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """No lock window used to appear at all (a free bypass); now SOLVE rows, one warning."""
    _plant({"version": 1, "entries": [_entry(hmac="é")]})

    with caplog.at_level(logging.WARNING):
        guard = _guard(tmp_path, hmac_key)
        guard.on_poll_result(probe_of("old-1"))
        guard.on_poll_result(probe_of("old-1"))
        shown = slugs_of(guard.model)

    assert shown == list(PREFIX)
    warned = [r for r in caplog.records if "review_due.json" in r.getMessage()]
    assert len(warned) == 1


def test_any_exception_in_the_review_read_is_cannot_check_with_one_warning(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog: pytest.LogCaptureFixture
):
    """The lock-side boundary, like the phase read: never into arming or the poll."""

    def boom(*_args: object, **_kwargs: object) -> DueRead:
        msg = "the reader blew up"
        raise RuntimeError(msg)

    monkeypatch.setattr("leetcode_guard._review_due.check_due", boom)
    with caplog.at_level(logging.WARNING):
        guard = _guard(tmp_path, hmac_key)
        guard.on_poll_result(probe_of("old-1"))
        guard.on_poll_result(probe_of("old-1"))
        guard.on_poll_result(probe_of("old-1"))
        shown = slugs_of(guard.model)

    assert shown == list(PREFIX)
    warned = [r for r in caplog.records if "blew up" in str(r.exc_info)]
    assert len(warned) == 1
    assert warned[0].levelno >= logging.WARNING


def test_the_watch_logs_one_line_with_the_reason(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """The reader is quiet; the watch's single record carries why."""
    watch = ReviewWatch(key_file=hmac_key)

    with caplog.at_level(logging.WARNING):
        answers = [watch.read((TARGET,), T_MS) for _ in range(4)]

    assert {a.status for a in answers} == {DueStatus.UNKNOWN}
    assert len(caplog.records) == 1
    assert "review_due.json" in caplog.records[0].getMessage()
