"""Tests for ledger persistence and the load-time integrity report."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import (
    Ledger,
    append,
    load_ledger,
    save_ledger,
    solved_slugs,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    forged_credit,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_round_trip(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    original = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    assert save_ledger(path, original)
    reloaded = load_ledger(path, key_file=hmac_key)

    assert len(reloaded.entries) == 3
    assert reloaded.tampered == 0
    assert reloaded.integrity_ok
    assert reloaded.unparsable == 0


def test_a_missing_ledger_loads_empty(tmp_path: Path, hmac_key: Path):
    ledger = load_ledger(tmp_path / "absent.json", key_file=hmac_key)

    assert ledger.entries == {}
    assert ledger.integrity_ok


@pytest.mark.parametrize(
    "content", ["not json", '["a"]', '{"no_entries": 1}', '{"entries": "nope"}']
)
def test_a_corrupt_ledger_loads_empty_and_logs_at_error(
    tmp_path: Path, hmac_key: Path, caplog, content: str
):
    """Empty means a zero balance, which locks rather than unlocks -- the right
    direction to fail, but it has to be diagnosable from the journal."""
    path = tmp_path / "ledger.json"
    path.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        ledger = load_ledger(path, key_file=hmac_key)

    assert ledger.entries == {}
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_an_unreadable_ledger_path_loads_empty(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    path.mkdir()

    assert load_ledger(path, key_file=hmac_key).entries == {}


def test_unparsable_rows_are_counted_not_silently_dropped(
    tmp_path: Path, hmac_key: Path
):
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({"version": 1, "entries": [{"junk": True}, {"also": "junk"}]}),
        encoding="utf-8",
    )

    ledger = load_ledger(path, key_file=hmac_key)

    assert ledger.unparsable == 2


def test_a_forged_entry_is_kept_and_counted_as_tampering(
    tmp_path: Path, hmac_key: Path
):
    """The inherited gatelock rule: never drop what you cannot verify."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    save_ledger(path, ledger)

    reloaded = load_ledger(path, key_file=hmac_key)

    assert reloaded.tampered == 1
    assert len(reloaded.entries) == 2
    assert not reloaded.entries["ac:forged"].verified


def test_an_unreadable_key_reports_integrity_off_without_flagging_tampering(
    tmp_path: Path, hmac_key: Path, missing_key: Path, caplog
):
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(2, day=MONDAY, key_file=hmac_key))

    with caplog.at_level(logging.WARNING):
        ledger = load_ledger(path, key_file=missing_key)

    assert not ledger.integrity_ok
    assert ledger.tampered == 0
    assert any(
        "integrity checking is OFF" in record.message for record in caplog.records
    )


def test_saving_creates_the_parent_directory(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "nested" / "ledger.json"

    assert save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))
    assert path.exists()


def test_a_failed_save_is_reported_not_raised(tmp_path: Path, hmac_key: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    assert not save_ledger(blocker / "ledger.json", Ledger())


def test_append_skips_ids_already_present():
    ledger = Ledger()
    first = LedgerEntry("ac:1", "credit", "2026-08-10", "", 1)
    duplicate = LedgerEntry("ac:1", "credit", "2026-07-28", "", 99)

    assert append(ledger, [first]) == 1
    assert append(ledger, [duplicate]) == 0
    assert ledger.entries["ac:1"].amount == 1


def test_of_kind_filters():
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry("ac:1", "credit", "2026-08-10", "", 1),
            LedgerEntry("charge:x", "charge", "2026-08-10", "", 1),
        ],
    )

    assert len(ledger.of_kind("credit")) == 1
    assert len(ledger.of_kind("charge")) == 1
    assert ledger.of_kind("seen") == []


def test_has():
    ledger = Ledger()
    append(ledger, [LedgerEntry("ac:1", "credit", "2026-08-10", "", 1)])

    assert ledger.has("ac:1")
    assert not ledger.has("ac:2")


def test_solved_slugs_collects_credits_and_seen_alike():
    """A `seen` entry is a solve that predates the gate, not a failure.

    It is worth zero credits on purpose, but for *suggestions* it means solved
    exactly as much as a credit does -- and on a freshly seeded ledger it is
    where nearly every known slug comes from, so dropping it would gut the
    filter.
    """
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                "ac:1", "credit", "2026-08-12", "", 1, detail={"title_slug": "a"}
            ),
            LedgerEntry(
                "ac:2", "seen", "2026-08-05", "", 0, detail={"title_slug": "b"}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset({"a", "b"})


def test_solved_slugs_ignores_entries_that_name_no_problem():
    """Charge and bootstrap entries carry no `title_slug` at all."""
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry("charge:2026-08-12", "charge", "2026-08-12", "", 1),
            LedgerEntry("bootstrap:2026-08-05", "bootstrap", "2026-08-05", "", 0),
            LedgerEntry(
                "ac:3", "credit", "2026-08-12", "", 1, detail={"title_slug": ""}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset()


def test_solved_slugs_of_an_empty_ledger_is_empty():
    assert solved_slugs(Ledger()) == frozenset()


def test_solved_slugs_deduplicates_repeated_solves():
    """Re-solving mints a fresh credit under a new submission id; the
    suggestion filter cares about the problem, not the attempt count."""
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                "ac:1", "credit", "2026-08-12", "", 1, detail={"title_slug": "a"}
            ),
            LedgerEntry(
                "ac:2", "credit", "2026-08-13", "", 1, detail={"title_slug": "a"}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset({"a"})


def test_saved_entries_keep_their_created_at(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))

    only = next(iter(load_ledger(path, key_file=hmac_key).entries.values()))

    assert only.created_at == NOW.isoformat()
