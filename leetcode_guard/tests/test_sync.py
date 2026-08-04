"""Tests for cross-device ledger sync.

The property that matters most is not that sync works -- it is that sync is
never load-bearing. A dead token, a 500 from GitHub, or a malformed remote file
must all leave the gate behaving exactly as it would offline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, GitHubSyncError, Record

from leetcode_guard import _sync
from leetcode_guard._ledger import LedgerEntry, to_json
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._sync import (
    _remote_client,
    entries_from_records,
    records_from_ledger,
    sync_ledger,
    sync_quietly,
)
from leetcode_guard._sync_token import read_sync_token
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    forged_credit,
    ledger_with_credits,
)

if TYPE_CHECKING:
    import pytest


class FakeSyncClient:
    """Stands in for GitHubSyncClient without touching the network."""

    def __init__(self, *, remote: dict | None = None, error: Exception | None = None):
        self.remote = remote if remote is not None else {}
        self.error = error


def fake_sync_log(monkeypatch, merged: dict | None = None, error=None) -> dict:
    """Replace crdt_sync.sync_log with a recorder."""
    seen: dict = {}

    def stub(*, local_log, **kwargs):
        seen["local"] = local_log
        seen["kwargs"] = kwargs
        if error is not None:
            raise error
        return merged if merged is not None else local_log

    monkeypatch.setattr("leetcode_guard._sync.sync_log", stub)
    return seen


# -- token -----------------------------------------------------------------


def test_a_missing_token_disables_sync_without_complaint(tmp_path: Path):
    assert read_sync_token(tmp_path / "absent") is None


def test_an_empty_token_is_refused(tmp_path: Path, caplog):
    path = tmp_path / "sync_token"
    path.write_text("   \n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert read_sync_token(path) is None


def test_an_unreadable_token_is_refused(tmp_path: Path):
    path = tmp_path / "sync_token"
    path.mkdir()

    assert read_sync_token(path) is None


def test_a_token_is_read_and_never_logged(tmp_path: Path, caplog):
    path = tmp_path / "sync_token"
    path.write_text("ghp_secretvalue\n", encoding="utf-8")

    with caplog.at_level(logging.DEBUG):
        token = read_sync_token(path)

    assert token == "ghp_secretvalue"
    assert not any("ghp_secretvalue" in record.message for record in caplog.records)


# -- projection ------------------------------------------------------------


def test_one_record_per_entry_never_a_running_total(hmac_key: Path):
    """A `balance` field would be last-write-wins and two devices would clobber
    each other's totals."""
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    log = records_from_ledger(ledger)

    assert len(log) == 3
    assert set(log) == set(ledger.entries)
    assert "balance" not in log


def test_the_clock_stamp_is_derived_from_the_entry_not_the_wall_clock(hmac_key: Path):
    """So re-pushing an unchanged ledger is byte-identical and produces no repo
    churn."""
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)

    first = records_from_ledger(ledger)
    second = records_from_ledger(ledger)

    for entry_id, record in first.items():
        assert record.fields["entry"][1] == second[entry_id].fields["entry"][1]


def test_an_unparsable_created_at_still_gets_a_deterministic_stamp(caplog):
    ledger = Ledger()
    append(ledger, [LedgerEntry("ac:1", "credit", "2026-08-10", "not-a-time", 1)])

    with caplog.at_level(logging.WARNING):
        log = records_from_ledger(ledger)

    assert log["ac:1"].fields["entry"][1].wall_time_ms == 0
    assert any("unparsable created_at" in record.message for record in caplog.records)


def test_records_round_trip_back_into_entries(hmac_key: Path):
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)

    restored = entries_from_records(records_from_ledger(ledger))

    assert {entry.entry_id for entry in restored} == set(ledger.entries)


def test_a_tombstoned_record_is_not_imported(hmac_key: Path):
    """Ledger entries are never deleted locally, so a tombstone came from
    elsewhere -- honour it by not importing rather than by deleting ours."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    log = records_from_ledger(ledger)
    only = next(iter(log))
    log[only] = Record(id=only, fields=log[only].fields, deleted=True)

    assert entries_from_records(log) == []


def test_a_record_with_no_payload_is_skipped(caplog):
    log = {"x": Record(id="x", fields={})}

    with caplog.at_level(logging.WARNING):
        assert entries_from_records(log) == []


def test_a_record_that_is_not_an_entry_is_skipped(caplog):
    from crdt_sync import Hlc

    log = {"x": Record(id="x", fields={"entry": ({"junk": 1}, Hlc(0, 0, "pc"))})}

    with caplog.at_level(logging.WARNING):
        assert entries_from_records(log) == []


# -- sync_ledger -----------------------------------------------------------


def test_no_token_means_sync_is_simply_off(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))

    result = sync_ledger(path, token_path=tmp_path / "absent", key_file=hmac_key)

    assert not result.pushed
    assert "no sync token" in result.reason


def test_a_successful_sync_reports_what_it_did(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(2, day=MONDAY, key_file=hmac_key))
    seen = fake_sync_log(monkeypatch)

    result = sync_ledger(path, key_file=hmac_key, client=FakeSyncClient())

    assert result.pushed
    assert result.record_count == 2
    assert seen["kwargs"]["device_id"] == "pc"
    assert seen["kwargs"]["filename"] == "ledger.json"


def test_a_github_failure_is_reported_not_raised(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog
):
    """Sync must never be able to keep the lock shut."""
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))
    fake_sync_log(monkeypatch, error=GitHubSyncError("500 from GitHub"))

    with caplog.at_level(logging.WARNING):
        result = sync_ledger(path, key_file=hmac_key, client=FakeSyncClient())

    assert not result.pushed
    assert "500 from GitHub" in result.reason


def test_remote_entries_are_merged_into_the_local_ledger(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    from crdt_sync import Hlc

    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))
    remote_entry = LedgerEntry(
        "ac:from-phone", "credit", "2026-08-10", NOW.isoformat(), 1, device="phone"
    )
    merged = {
        "ac:from-phone": Record(
            id="ac:from-phone",
            fields={"entry": (to_json(remote_entry), Hlc(1, 0, "phone"))},
        )
    }
    fake_sync_log(monkeypatch, merged=merged)

    result = sync_ledger(path, key_file=hmac_key, client=FakeSyncClient())

    assert result.merged_in == 1
    assert load_ledger(path, key_file=hmac_key).has("ac:from-phone")


def test_a_synced_credit_still_has_to_verify_before_it_counts(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The sync repo is a user-writable channel. Committing JSON must not be a
    way to mint credits."""
    from crdt_sync import Hlc

    from leetcode_guard._balance import compute_balance

    path = tmp_path / "ledger.json"
    save_ledger(path, Ledger())
    forged = forged_credit("ac:committed-by-hand")
    merged = {
        forged.entry_id: Record(
            id=forged.entry_id,
            fields={"entry": (to_json(forged), Hlc(1, 0, "phone"))},
        )
    }
    fake_sync_log(monkeypatch, merged=merged)

    sync_ledger(path, key_file=hmac_key, client=FakeSyncClient())
    balance = compute_balance(load_ledger(path, key_file=hmac_key))

    assert balance.credits == 0
    assert balance.discounted == 1


def test_syncing_an_unchanged_ledger_merges_nothing(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(2, day=MONDAY, key_file=hmac_key))
    fake_sync_log(monkeypatch)

    result = sync_ledger(path, key_file=hmac_key, client=FakeSyncClient())

    assert result.merged_in == 0


def test_sync_quietly_swallows_anything(tmp_path: Path, monkeypatch, caplog):
    """Called from the lock's close path, where an exception would abort
    teardown and leave the screen grabbed."""

    def explode(*_args, **_kwargs):
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr("leetcode_guard._sync.sync_ledger", explode)

    with caplog.at_level(logging.ERROR):
        result = sync_quietly(tmp_path / "ledger.json")

    assert not result.pushed
    assert result.reason == "sync raised"


def test_sync_quietly_passes_a_success_through(tmp_path: Path, hmac_key: Path):
    result = sync_quietly(tmp_path / "ledger.json", token_path=tmp_path / "absent")

    assert not result.pushed
    assert "no sync token" in result.reason


def test_the_encode_decode_pair_round_trips(hmac_key: Path):
    """These are handed to crdt_sync as callbacks, so nothing else exercises
    them -- but a mismatch would corrupt every device file."""
    from leetcode_guard._sync import _decode, _encode

    log = records_from_ledger(ledger_with_credits(2, day=MONDAY, key_file=hmac_key))

    restored = _decode(_encode(log))

    assert set(restored) == set(log)


def test_a_present_token_builds_a_real_client(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Covers the branch that constructs GitHubSyncClient; the client itself is
    never called because sync_log is stubbed."""
    token = tmp_path / "sync_token"
    token.write_text("ghp_test", encoding="utf-8")
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))
    fake_sync_log(monkeypatch)

    result = sync_ledger(path, token_path=token, key_file=hmac_key)

    assert result.pushed


def test_remote_client_stays_on_github_without_firebase_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured machine must not reach the network at all."""
    monkeypatch.setattr(_sync, "CONFIG_FILE", Path("/nonexistent/firebase.json"))
    github = object()

    assert _remote_client(github) is github


def test_remote_client_mirrors_to_github_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured: Firebase is primary, GitHub keeps receiving the writes."""
    config = tmp_path / "firebase.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_sync, "CONFIG_FILE", config)
    monkeypatch.setattr(
        _sync, "mirror_client_for", lambda _app, client: ("mirror", client)
    )
    github = object()

    assert _remote_client(github) == ("mirror", github)


def test_remote_client_falls_back_when_firebase_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken Firebase must degrade to GitHub, never fail the tick."""
    config = tmp_path / "firebase.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_sync, "CONFIG_FILE", config)

    def _boom(*_args: object, **_kwargs: object) -> None:
        message = "no password"
        raise ConfigError(message)

    monkeypatch.setattr(_sync, "mirror_client_for", _boom)
    github = object()

    assert _remote_client(github) is github
