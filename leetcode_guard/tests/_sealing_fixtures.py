"""Suite-wide E2E rail, as a pytest plugin.

Every test sees a passphrase in ``tmp_path``, never the real
``~/.config/crdt-sync/password`` (``PASSWORD_FILE`` is resolved at import, so
redirecting ``HOME`` would not help), and Argon2 at a test cost. The ledger
sync's Firebase probe is pointed at a missing file for the same reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync import Argon2Params, reset_e2e_copy_memo
import pytest

from leetcode_guard import _e2e, _sync

if TYPE_CHECKING:
    from pathlib import Path

TEST_PASSPHRASE = "test-passphrase"
TEST_PARAMS = Argon2Params(memory_kib=8, iterations=1, parallelism=1)


@pytest.fixture(autouse=True)
def _inject_passphrase(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A test passphrase file and a cheap Argon2; returns the file."""
    secret = tmp_path / "crdt-sync" / "password"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(f"{TEST_PASSPHRASE}\n", encoding="utf-8")
    monkeypatch.setattr(_e2e, "PASSWORD_PATH", secret)
    monkeypatch.setattr(_e2e, "PARAMS", TEST_PARAMS)
    monkeypatch.setattr(_e2e, "STATE_DIR", tmp_path / "e2e-state")
    monkeypatch.setattr(_sync, "CONFIG_FILE", tmp_path / "crdt-sync" / "firebase.json")
    reset_e2e_copy_memo()
    return secret
