"""Continued from :mod:`leetcode_guard.tests.test_sync`, split for the 250-line cap."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, Record

from leetcode_guard import _sync
from leetcode_guard._ledger import to_json
from leetcode_guard._ledger_io import Ledger, load_ledger, save_ledger
from leetcode_guard._sync import (
    _remote_client,
    records_from_ledger,
    sync_ledger,
    sync_quietly,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    forged_credit,
    ledger_with_credits,
)

if TYPE_CHECKING:
    import pytest


from leetcode_guard.tests.test_sync import (
    FakeSyncClient,
    fake_sync_log,
)


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
    from leetcode_guard._sync_records import decode_log, encode_log

    log = records_from_ledger(ledger_with_credits(2, day=MONDAY, key_file=hmac_key))

    restored = decode_log(encode_log(log))

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
