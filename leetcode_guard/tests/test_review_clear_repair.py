"""The one-off repair of the 2026-11-24 review clear (part 9005c9b4-1).

Evidence: that day's signed review rows of the unit, a ``charge:<day>`` row,
and a signed due row written after the day that puts every card of the unit
after it. It mints through the live rule's own entry builder, with
``detail.repair: "true"``, at most once.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard import _cli, _review_clear_cli, _tutor_signed
from leetcode_guard._ledger import CHARGE, LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._review_clear import clear_id
from leetcode_guard._review_clear_repair import Repair, repair_review_clear
from leetcode_guard.tests._review_fixtures import DAY, put, reviews
from leetcode_guard.tests._theory_scenario import states, world
from leetcode_guard.tests._tutor_fixtures import due_row, write_due

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

AFTER = datetime(2026, 11, 26, 12, 30).astimezone()
"""The newest due row: written two days after the reviewed day."""
END_MS = int(datetime(2026, 11, 25).astimezone().timestamp() * 1000)
CARDS = [END_MS + 86_400_000, END_MS + 10 * 86_400_000]
NOW = datetime(2026, 11, 27, 11, 0).astimezone()


def _charged() -> Ledger:
    ledger = Ledger()
    charge = LedgerEntry(
        entry_id=f"charge:{DAY.isoformat()}",
        kind=CHARGE,
        day=DAY.isoformat(),
        created_at=NOW.isoformat(),
        amount=2,
        detail={"source": "leetcode"},
    )
    append(ledger, [charge])
    return ledger


def _evidence(tmp_path, monkeypatch, key: Path, *, cards=None, at=AFTER) -> None:
    world(tmp_path, monkeypatch)
    states(key, "a")
    put(reviews(key, "a", 6))
    times = CARDS if cards is None else cards
    write_due([due_row("a", times, at=at.timestamp(), key_file=key)])


def _repair(ledger: Ledger, key: Path) -> Repair:
    return repair_review_clear(ledger, day=DAY, unit="a", now=NOW, key_file=key)


def test_the_evidence_mints_one_repair_credit(tmp_path, monkeypatch, hmac_key: Path):
    """Reviews on the day, a charge, every card after the day: minted once."""
    _evidence(tmp_path, monkeypatch, hmac_key)
    ledger = _charged()

    assert _repair(ledger, hmac_key) == Repair.MINTED
    row = ledger.entries[clear_id(DAY, "a")]
    assert (row.kind, row.amount, row.day) == ("credit", 1, DAY.isoformat())
    assert row.detail["repair"] == "true"
    assert row.detail["source"] == "tutor-theory"
    assert row.detail["cards"] == "2"
    assert _repair(ledger, hmac_key) == Repair.ALREADY


def test_a_card_due_on_the_day_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """A card due before the day ended was not cleared."""
    _evidence(tmp_path, monkeypatch, hmac_key, cards=[END_MS - 1, *CARDS])

    assert _repair(_charged(), hmac_key) == Repair.REFUSED


def test_a_due_row_from_the_day_itself_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """The due row must be written after the day ended."""
    on_day = datetime(2026, 11, 24, 19, 0).astimezone()
    _evidence(tmp_path, monkeypatch, hmac_key, at=on_day)

    assert _repair(_charged(), hmac_key) == Repair.REFUSED


def test_no_review_on_the_day_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """Without the signed review rows there is nothing to repair."""
    _evidence(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "b1", 6))

    assert _repair(_charged(), hmac_key) == Repair.REFUSED


def test_no_charge_for_the_day_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """The day must have been a gated, settled day."""
    _evidence(tmp_path, monkeypatch, hmac_key)

    assert _repair(Ledger(), hmac_key) == Repair.REFUSED


def test_an_unmapped_unit_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """A unit the curriculum does not know has no modules to check."""
    _evidence(tmp_path, monkeypatch, hmac_key)
    ledger = _charged()

    got = repair_review_clear(ledger, day=DAY, unit="zz", now=NOW, key_file=hmac_key)

    assert got == Repair.REFUSED


def test_an_unreadable_due_file_refuses(tmp_path, monkeypatch, hmac_key: Path):
    """Cannot check is a refusal, never a mint."""
    _evidence(tmp_path, monkeypatch, hmac_key)
    (_tutor_signed.TUTOR_DIR / "review_due.json").unlink()

    assert _repair(_charged(), hmac_key) == Repair.REFUSED


def test_the_cli_mints_then_says_already(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    capsys: pytest.CaptureFixture[str],
):
    """``--repair-review-clear`` prints what it did; a rerun writes nothing."""
    _evidence(tmp_path, monkeypatch, hmac_key)
    path = data_dir / "ledger.json"
    save_ledger(path, _charged())
    monkeypatch.setattr(_review_clear_cli, "LEDGER_FILE", path)
    monkeypatch.setattr(_review_clear_cli, "REPAIR", (DAY, "a"))
    monkeypatch.setattr(_review_clear_cli, "KEY_FILE", hmac_key)
    monkeypatch.setattr(_review_clear_cli, "now_local", lambda: NOW)

    first = _cli.main(["--repair-review-clear"])
    out = capsys.readouterr().out
    second = _cli.main(["--repair-review-clear"])
    again = capsys.readouterr().out

    assert f"minted {clear_id(DAY, 'a')}" in out
    assert f"already minted {clear_id(DAY, 'a')}" in again
    assert (first, second) == (0, 0)
    assert load_ledger(path, key_file=hmac_key).has(clear_id(DAY, "a"))


def test_the_cli_refusal_says_why(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    capsys: pytest.CaptureFixture[str],
):
    """No evidence: a refusal line and a non-zero exit, nothing written."""
    world(tmp_path, monkeypatch)
    path = data_dir / "ledger.json"
    save_ledger(path, _charged())
    monkeypatch.setattr(_review_clear_cli, "LEDGER_FILE", path)
    monkeypatch.setattr(_review_clear_cli, "REPAIR", (DAY, "a"))
    monkeypatch.setattr(_review_clear_cli, "KEY_FILE", hmac_key)
    monkeypatch.setattr(_review_clear_cli, "now_local", lambda: NOW)

    assert _cli.main(["--repair-review-clear"]) != 0
    assert "refused" in capsys.readouterr().out
    assert not load_ledger(path, key_file=hmac_key).has(clear_id(DAY, "a"))


def test_the_live_constants_name_the_reported_day():
    """kuhy's report: the 2026-11-24 review of prefix-sums."""
    day, unit = _review_clear_cli.REPAIR
    assert (day.isoformat(), unit) == ("2026-11-24", "prefix-sums")
    assert _review_clear_cli.KEY_FILE is None
    assert abs(_review_clear_cli.now_local() - datetime.now().astimezone()) < timedelta(
        minutes=1
    )
