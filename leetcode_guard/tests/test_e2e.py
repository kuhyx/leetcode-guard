"""End-to-end encryption: nothing leetcode-guard syncs reaches a backend in clear.

Real crdt_sync E2E code over an in-memory remote. The red check is the
backend's view: no field name or value of ours appears in any blob.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from crdt_sync import E2eLayout, load_log, reset_e2e_copy_memo, unlock_e2e

from leetcode_guard import _e2e, _phone_errors_sync, _snapshot_dedup, _snapshot_push
from leetcode_guard._e2e import APP_ERRORS_LAYOUT, SNAPSHOT_LAYOUT, sealed
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._snapshot_push import (
    HEARTBEAT_PATH,
    SNAPSHOT_PATH,
    STATUS_HASH_PATH,
    push_snapshot,
)
from leetcode_guard._sync import SYNC_PATH_PREFIX, sync_ledger
from leetcode_guard.tests._ledger_fixtures import MONDAY, ledger_with_credits
from leetcode_guard.tests._memory_remote import MemoryRemote
from leetcode_guard.tests._sealing_fixtures import TEST_PARAMS, TEST_PASSPHRASE

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SNAPSHOT = {"schema": 1, "balance": {"credits": 7}, "generated_at": "2026-11-12T10:00"}


def _key(remote: MemoryRemote, layout: E2eLayout) -> object:
    """The key a second device derives from the same passphrase."""
    return unlock_e2e(
        remote,
        path_prefix=layout.prefix,
        passphrase=TEST_PASSPHRASE,
        params=TEST_PARAMS,
        e2e_path=layout.e2e_path,
    )


def _sealed_push(monkeypatch: pytest.MonkeyPatch, remote: MemoryRemote) -> None:
    """Route the production push's sign-in and silent writer to ``remote``."""
    monkeypatch.setattr(_snapshot_push, "sign_in", lambda *_a, **_k: remote)
    monkeypatch.setattr(_snapshot_push, "silent_store_for", lambda *_a, **_k: remote)


def test_the_snapshot_leaves_live_under_their_own_e2e_prefix():
    """status, hash and heartbeat move together under ``snapshot-e2e``."""
    assert SNAPSHOT_PATH == "leetcode-guard/snapshot-e2e/status"
    assert STATUS_HASH_PATH == "leetcode-guard/snapshot-e2e/status_hash"
    assert HEARTBEAT_PATH == "leetcode-guard/snapshot-e2e/heartbeat"


def test_snapshot_and_errors_share_one_header_and_leave_coach_alone():
    """One Argon2 run opens both; the shared coach node is outside both."""
    assert (
        SNAPSHOT_LAYOUT.e2e_path == APP_ERRORS_LAYOUT.e2e_path == "leetcode-guard/e2e"
    )
    assert APP_ERRORS_LAYOUT.prefix == "leetcode-guard/app_errors-e2e"
    for layout in (SNAPSHOT_LAYOUT, APP_ERRORS_LAYOUT):
        assert not layout.prefix.startswith("leetcode-guard/coach")


def test_a_pushed_snapshot_is_ciphertext_to_the_backend(
    monkeypatch: pytest.MonkeyPatch,
):
    """The RTDB sees no field name or value; the phone's key opens it."""
    remote = MemoryRemote()
    _sealed_push(monkeypatch, remote)

    result = push_snapshot(SNAPSHOT)

    assert result.pushed
    for path in (SNAPSHOT_PATH, STATUS_HASH_PATH, HEARTBEAT_PATH):
        stored = remote.data[path]
        assert "balance" not in stored
        assert "credits" not in stored
        assert "2026-11-12" not in stored
    phone = sealed(remote, _key(remote, SNAPSHOT_LAYOUT), SNAPSHOT_LAYOUT)
    assert json.loads(phone.get_file_text(SNAPSHOT_PATH) or "") == SNAPSHOT
    assert phone.get_file_text(HEARTBEAT_PATH) == SNAPSHOT["generated_at"]


def test_a_locked_push_writes_nothing(monkeypatch: pytest.MonkeyPatch):
    """No passphrase: the tick is skipped, plaintext is never the fallback."""
    _e2e.PASSWORD_PATH.unlink()
    remote = MemoryRemote()
    _sealed_push(monkeypatch, remote)

    result = push_snapshot(SNAPSHOT)

    assert not result.pushed
    assert "passphrase" in result.reason
    assert remote.writes == []


def test_a_hash_recorded_for_the_old_path_does_not_skip_the_first_push(
    monkeypatch: pytest.MonkeyPatch,
):
    """After the move, the old dedup state must not leave the new node empty."""
    _snapshot_dedup.PUSH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _snapshot_dedup.PUSH_STATE_FILE.write_text(
        json.dumps({"hash": _snapshot_dedup.content_hash(SNAPSHOT)}),
        encoding="utf-8",
    )
    remote = MemoryRemote()
    _sealed_push(monkeypatch, remote)

    push_snapshot(SNAPSHOT)

    assert SNAPSHOT_PATH in remote.data


def test_the_ledger_is_ciphertext_to_the_backend(tmp_path: Path, hmac_key: Path):
    """The ledger log lands under ``devices-e2e`` with entry payloads sealed.

    Record ids stay clear by design (the recipe's scope is the payload).
    """
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(2, day=MONDAY, key_file=hmac_key))
    remote = MemoryRemote()

    result = sync_ledger(path, key_file=hmac_key, client=remote)

    assert result.pushed
    layout = E2eLayout.of(SYNC_PATH_PREFIX)
    blobs = {p: t for p, t in remote.data.items() if p.startswith(f"{layout.prefix}/")}
    assert blobs
    for text in blobs.values():
        assert "created_at" not in text
        assert '"entry"' not in text
    assert not any(p.startswith(f"{SYNC_PATH_PREFIX}/") for p in remote.data)
    peer = sealed(remote, _key(remote, layout), layout)
    opened = load_log(peer.get_file_text(next(iter(blobs))) or "")
    assert len(opened) == 2


def test_a_locked_ledger_sync_writes_nothing(tmp_path: Path, hmac_key: Path):
    """No passphrase: an unpushed result, and the backend untouched."""
    _e2e.PASSWORD_PATH.unlink()
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(1, day=MONDAY, key_file=hmac_key))
    remote = MemoryRemote()

    result = sync_ledger(path, key_file=hmac_key, client=remote)

    assert not result.pushed
    assert "locked" in result.reason
    assert remote.writes == []


def test_sealed_phone_errors_come_back_decrypted(monkeypatch: pytest.MonkeyPatch):
    """The phone seals one leaf per device; the PC bulk-reads them opened."""
    remote = MemoryRemote()
    body = {"errors": [{"message": "boom"}]}
    phone = sealed(remote, _key(remote, APP_ERRORS_LAYOUT), APP_ERRORS_LAYOUT)
    phone.put_file_text(
        f"{APP_ERRORS_LAYOUT.prefix}/dev-1", json.dumps(body), message="errors"
    )
    remote.data[f"{APP_ERRORS_LAYOUT.prefix}/dev-2"] = '{"v":1,"b":"AQID"}'
    assert "boom" not in remote.data[f"{APP_ERRORS_LAYOUT.prefix}/dev-1"]
    monkeypatch.setattr(_phone_errors_sync, "sign_in", lambda *_a, **_k: remote)

    assert _phone_errors_sync.fetch_phone_errors() == {"dev-1": json.dumps(body)}


def test_the_next_minute_reuses_the_cached_key(monkeypatch: pytest.MonkeyPatch):
    """The harvester is a new process each minute: Argon2 runs once."""
    remote = MemoryRemote()
    _sealed_push(monkeypatch, remote)
    first = _e2e.unlock_shared(remote)
    derived: list[object] = []

    def derive(*args: object) -> object:
        """Record a derivation the cache should have made unnecessary."""
        derived.append(args)
        return first

    monkeypatch.setattr("crdt_sync._e2e_key.derive_key", derive)
    reset_e2e_copy_memo()

    assert _e2e.unlock_shared(remote).master == first.master
    assert derived == []
    assert any(_e2e.STATE_DIR.iterdir())
