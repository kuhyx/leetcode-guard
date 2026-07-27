"""Tests for credit harvesting and first-run seeding."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard._harvest import (
    commit_harvest,
    harvest,
    needs_seeding,
    seed_ledger,
)
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    ledger_with_credits,
    submission,
)

if TYPE_CHECKING:
    from pathlib import Path


def probe_of(*ids: str) -> SolveProbe:
    return SolveProbe(
        status=ProbeStatus.OK,
        submissions=tuple(submission(item) for item in ids),
        reason=f"{len(ids)} recent",
    )


UNVERIFIABLE = SolveProbe(
    status=ProbeStatus.UNVERIFIABLE, submissions=(), reason="cannot reach LeetCode"
)


def test_every_unseen_submission_becomes_one_credit(hmac_key: Path):
    result = harvest(
        Ledger(), probe_of("a", "b", "c"), day=MONDAY, now=NOW, key_file=hmac_key
    )

    assert result.gained == 3
    assert result.already_known == 0
    assert {entry.entry_id for entry in result.new_credits} == {"ac:a", "ac:b", "ac:c"}


def test_an_unverifiable_probe_mints_nothing_and_keeps_its_status(hmac_key: Path):
    """The single most important guard: "cannot check" must never look like
    "nothing new"."""
    result = harvest(Ledger(), UNVERIFIABLE, day=MONDAY, now=NOW, key_file=hmac_key)

    assert result.gained == 0
    assert result.status is ProbeStatus.UNVERIFIABLE
    assert "cannot reach" in result.reason


def test_an_empty_but_ok_probe_is_a_real_zero(hmac_key: Path):
    result = harvest(Ledger(), probe_of(), day=MONDAY, now=NOW, key_file=hmac_key)

    assert result.gained == 0
    assert result.status is ProbeStatus.OK


def test_harvest_does_not_mutate_the_ledger(hmac_key: Path):
    ledger = Ledger()

    harvest(ledger, probe_of("a"), day=MONDAY, now=NOW, key_file=hmac_key)

    assert ledger.entries == {}


def test_commit_persists_and_is_a_no_op_when_empty(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    result = harvest(ledger, probe_of("a"), day=MONDAY, now=NOW, key_file=hmac_key)

    assert commit_harvest(ledger, result, path)
    assert load_ledger(path, key_file=hmac_key).has("ac:a")

    empty = harvest(ledger, probe_of("a"), day=MONDAY, now=NOW, key_file=hmac_key)
    assert not commit_harvest(ledger, empty, path)


def test_needs_seeding_is_true_for_an_empty_but_present_ledger(hmac_key: Path):
    """Keyed on the bootstrap marker, not on the file's absence -- otherwise an
    empty file would skip seeding and hand out the whole recent feed."""
    assert needs_seeding(Ledger())
    assert needs_seeding(ledger_with_credits(2, day=MONDAY, key_file=hmac_key))


def test_seeding_marks_submissions_without_granting_credit(
    tmp_path: Path, hmac_key: Path, caplog
):
    path = tmp_path / "ledger.json"
    ledger = Ledger()

    with caplog.at_level(logging.WARNING):
        seeded = seed_ledger(
            ledger,
            probe_of("a", "b"),
            day=MONDAY,
            now=NOW,
            path=path,
            key_file=hmac_key,
        )

    assert seeded == 2
    assert not needs_seeding(ledger)
    assert (
        harvest(
            ledger, probe_of("a", "b"), day=MONDAY, now=NOW, key_file=hmac_key
        ).gained
        == 0
    )
    assert any("grant no credit" in record.message for record in caplog.records)


def test_seeding_refuses_an_unverifiable_probe(tmp_path: Path, hmac_key: Path, caplog):
    """Seeding off a probe we could not read would write a marker covering
    nothing, and the next tick would harvest the whole feed as credits."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()

    with caplog.at_level(logging.WARNING):
        result = seed_ledger(
            ledger, UNVERIFIABLE, day=MONDAY, now=NOW, path=path, key_file=hmac_key
        )

    assert result == -1
    assert needs_seeding(ledger)
    assert not path.exists()


def test_seeding_an_empty_feed_still_records_the_marker(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = Ledger()

    assert (
        seed_ledger(
            ledger, probe_of(), day=MONDAY, now=NOW, path=path, key_file=hmac_key
        )
        == 0
    )
    assert not needs_seeding(ledger)


def test_seeded_markers_survive_a_reload(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    seed_ledger(
        ledger, probe_of("a"), day=MONDAY, now=NOW, path=path, key_file=hmac_key
    )

    reloaded = load_ledger(path, key_file=hmac_key)

    assert not needs_seeding(reloaded)
    assert reloaded.tampered == 0
    assert (
        harvest(reloaded, probe_of("a"), day=MONDAY, now=NOW, key_file=hmac_key).gained
        == 0
    )
