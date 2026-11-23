"""The re-pass credit: +1 per post-mortem revision, only for a real re-pass today."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import Ledger
from leetcode_guard._phase import PhaseState
from leetcode_guard._theory_redone import REVISIONS, due_redone, revisions
from leetcode_guard.tests._finish_fixtures import (
    DAY,
    NOW,
    TODAY,
    YESTERDAY,
    flips,
    ids,
    poll,
)
from leetcode_guard.tests._theory_scenario import began, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO, signed, write_tutor

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

REDONE = f"theory-redone:{ALGO}:a:1"
REV_AT = YESTERDAY + 60


def rev_row(key: Path, **detail: object) -> dict[str, object]:
    """A signed C7 row for unit a, revision 1, overridden by ``detail``."""
    body = {"unit": "a", "subject": ALGO, "modules": ["a"], "rev": 1, "at": REV_AT}
    row = {"kind": "postmortem_rev", "entry_id": "pm:a:1", "day": str(DAY)}
    return signed({**row, "detail": {**body, **detail}}, key)


def redone_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: Path) -> None:
    """Unit a done, post-mortem revision 1, un-done after it, done again today."""
    world(tmp_path, monkeypatch)
    began(key)
    write_tutor(REVISIONS, [rev_row(key)])
    flips(key, ("a", True, YESTERDAY), ("a", False, REV_AT + 1), ("a", True, TODAY))


def test_a_re_pass_today_pays_one_credit_once(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """The credit is a signed tutor-theory row; a second poll mints nothing."""
    redone_world(tmp_path, monkeypatch, hmac_key)
    taught(hmac_key, NOW, ("a", 3))  # C1 must be readable for any theory credit
    ledger = Ledger()

    result = poll(ledger, data_dir, hmac_key)

    assert REDONE in ids(result)
    entry = next(e for e in result.minted if e.entry_id == REDONE)
    shape = {"kind": entry.kind, "amount": entry.amount, "day": entry.day}
    assert shape == {"kind": "credit", "amount": 1, "day": str(DAY)}
    want = {"source": "tutor-theory", "unit": "a", "rev": "1", "redone": "1"}
    assert entry.detail == {**want, "subject": ALGO}
    assert REDONE not in ids(poll(ledger, data_dir, hmac_key))


AT_A = PhaseState("a", "theory", ALGO, ("a",))
AT_B = PhaseState("b", "theory", ALGO, ("b1", "b2"))


def due(
    key: Path, state: PhaseState = AT_A, before: PhaseState | None = None
) -> list[str]:
    """The ids ``due_redone`` would mint now."""
    found = due_redone(Ledger(), state, before, stamp=(DAY, NOW), key_file=key)
    return [entry.entry_id for entry in found]


def test_the_unit_must_be_current_at_the_start_or_end_of_the_poll(
    tmp_path, monkeypatch, hmac_key: Path
):
    """Finishing the re-pass moves the machine on: ``before`` still pays it."""
    redone_world(tmp_path, monkeypatch, hmac_key)

    assert due(hmac_key) == [REDONE]
    assert due(hmac_key, AT_B, AT_A) == [REDONE]
    assert due(hmac_key, AT_B) == []
    assert due(hmac_key, AT_B, PhaseState("", "none", "", ())) == []


def test_no_re_pass_no_credit(tmp_path, monkeypatch, hmac_key: Path):
    """A re-signed done with no undo, an undo still open, or a done not today."""
    redone_world(tmp_path, monkeypatch, hmac_key)
    flips(hmac_key, ("a", True, YESTERDAY), ("a", True, TODAY))
    assert due(hmac_key) == []
    flips(hmac_key, ("a", True, YESTERDAY), ("a", False, TODAY))
    assert due(hmac_key) == []
    flips(hmac_key, ("a", False, REV_AT + 1), ("a", True, REV_AT + 2))
    assert due(hmac_key) == []
    flips(hmac_key, ("b1", False, REV_AT + 1), ("b1", True, TODAY))
    assert due(hmac_key) == []
    odd = signed({"kind": "module_state", "detail": {"done": "x"}}, hmac_key)
    write_tutor("module_state.json", [odd])
    assert due(hmac_key) == []
    write_tutor("module_state.json", [{"kind": "module_state", "hmac": "x"}])
    assert due(hmac_key) == []


def test_a_missing_file_is_silent_and_a_bad_row_never_pays(
    tmp_path, monkeypatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """No file: no rows, no log line. Forged or malformed rows are dropped."""
    world(tmp_path, monkeypatch)
    with caplog.at_level(logging.WARNING):
        assert revisions(hmac_key) == []
    assert caplog.text == ""

    bad = [
        {**rev_row(hmac_key), "hmac": "0" * 64},
        signed({"kind": "other", "detail": {}}, hmac_key),
        rev_row(hmac_key, at=True),
        rev_row(hmac_key, rev="1"),
        rev_row(hmac_key, rev=True),
        rev_row(hmac_key, unit=1),
        rev_row(hmac_key, subject=None),
        rev_row(hmac_key, modules=[]),
        rev_row(hmac_key, modules="a"),
    ]
    write_tutor(REVISIONS, bad)
    assert revisions(hmac_key) == []


def test_two_rows_of_one_revision_pay_once(tmp_path, monkeypatch, hmac_key: Path):
    """The same id twice in C7 (a retried write) is one credit."""
    redone_world(tmp_path, monkeypatch, hmac_key)
    write_tutor(REVISIONS, [rev_row(hmac_key), rev_row(hmac_key)])

    assert due(hmac_key) == [REDONE]
