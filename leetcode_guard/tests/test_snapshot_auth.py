"""Tests for the pusher's Firebase sign-in and its sibling-session heal.

Measured 2026-10-23: the shared password in ``~/.config/crdt-sync/password``
answers ``INVALID_LOGIN_CREDENTIALS``, while a dozen sibling apps hold live
refresh tokens for the same account -- the 2026-08-24 screen-locker failure,
which ``screen_locker/_credential_recovery.py`` heals the same way.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

from crdt_sync import (
    ConfigError,
    FileCredentialStore,
    FirebaseAuthError,
    FirebaseCredentials,
)
import pytest

from leetcode_guard import _snapshot_auth
from leetcode_guard._snapshot_auth import adopt_sibling_session, connect

if TYPE_CHECKING:
    from pathlib import Path

APP = "leetcode_guard_status"
LATER = datetime(2030, 1, 1, tzinfo=UTC)
OLD_ID, FRESH_ID, ROTATED = "old", "fresh", "rotated"


def seed(root: Path, app: str, refresh: str) -> Path:
    path = root / app / "firebase_auth.json"
    FileCredentialStore(path).save(
        FirebaseCredentials(id_token=OLD_ID, refresh_token=refresh, expires_at=LATER)
    )
    return path


def minted(refresh_token: str) -> FirebaseCredentials:
    if refresh_token.startswith("dead"):
        message = "TOKEN_EXPIRED"
        raise FirebaseAuthError(message)
    return FirebaseCredentials(
        id_token=f"id-for-{refresh_token}",
        refresh_token=refresh_token,
        expires_at=LATER,
    )


def test_a_live_sibling_seeds_our_own_cache(tmp_path: Path):
    seed(tmp_path, "aaa_dead", "dead-1")
    seed(tmp_path, "wake_alarm", "live-2")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "firebase_auth.json").write_text("{", encoding="utf-8")

    donor = adopt_sibling_session(APP, config_root=tmp_path, mint=minted)

    assert donor == "wake_alarm"
    ours = FileCredentialStore(tmp_path / APP / "firebase_auth.json").load()
    assert ours is not None
    assert ours.id_token == "id-for-live-2"


def test_our_own_cache_is_never_its_own_donor(tmp_path: Path):
    seed(tmp_path, APP, "live-own")

    assert adopt_sibling_session(APP, config_root=tmp_path, mint=minted) is None


def test_every_dead_sibling_means_no_session(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    seed(tmp_path, "a", "dead-1")
    seed(tmp_path, "b", "dead-2")

    assert adopt_sibling_session(APP, config_root=tmp_path, mint=minted) is None
    assert caplog.text.count("was rejected") == 2


def test_connect_uses_the_cached_session_first(tmp_path: Path):
    calls: list[str] = []

    def client_for(app: str, *, timeout_seconds: float) -> object:
        calls.append(app)
        return "client"

    assert connect(APP, timeout_seconds=1.0, client_for=client_for) == "client"
    assert calls == [APP]


def test_connect_heals_from_a_sibling_after_a_failed_sign_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    seed(tmp_path, "diet_guard", "live-9")
    attempts: list[str] = []

    def client_for(app: str, *, timeout_seconds: float) -> object:
        attempts.append(app)
        if len(attempts) == 1:
            message = "failed to sign in: HTTP 400 (INVALID_LOGIN_CREDENTIALS)"
            raise FirebaseAuthError(message)
        return "healed"

    result = connect(
        APP,
        timeout_seconds=1.0,
        client_for=client_for,
        config_root=tmp_path,
        mint=minted,
    )

    assert result == "healed"
    assert "INVALID_LOGIN_CREDENTIALS" in caplog.text
    assert "diet_guard" in caplog.text


def test_connect_reraises_when_no_sibling_can_help(tmp_path: Path):
    def client_for(app: str, *, timeout_seconds: float) -> object:
        message = "missing firebase.json"
        raise ConfigError(message)

    with pytest.raises(FirebaseAuthError, match="no sibling app"):
        connect(
            APP,
            timeout_seconds=1.0,
            client_for=client_for,
            config_root=tmp_path,
            mint=minted,
        )


def test_the_real_mint_exchanges_through_the_public_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    config = tmp_path / "firebase.json"
    config.write_text(
        json.dumps(
            {
                "apiKey": "k",
                "databaseUrl": "https://x",
                "projectId": "p",
                "uid": "u",
                "email": "e@x",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_snapshot_auth, "CONFIG_FILE", config)
    seen: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, api_key: str, store: object) -> None:
            seen["api_key"] = api_key
            self.store = store

        def id_token(self) -> str:
            old = self.store.load()
            seen["refreshing"] = old.refresh_token
            seen["expired"] = old.is_expired_at(datetime.now(tz=UTC))
            self.store.save(
                FirebaseCredentials(
                    id_token=FRESH_ID, refresh_token=ROTATED, expires_at=LATER
                )
            )
            return "fresh"

    monkeypatch.setattr(_snapshot_auth, "FirebaseTokenProvider", FakeProvider)

    credentials = _snapshot_auth.mint_from_refresh_token("borrowed")

    assert seen == {"api_key": "k", "refreshing": "borrowed", "expired": True}
    assert (credentials.id_token, credentials.refresh_token) == ("fresh", "rotated")


def test_a_provider_that_stores_nothing_is_an_auth_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class Forgetful:
        def __init__(self, api_key: str, store: object) -> None:
            self.store = store

        def id_token(self) -> str:
            self.store.clear()
            return ""

    monkeypatch.setattr(_snapshot_auth, "FirebaseTokenProvider", Forgetful)
    monkeypatch.setattr(
        _snapshot_auth.FirebaseConfig,
        "load",
        classmethod(lambda cls, path=None: cls("k", "https://x", "p", "u", "e")),
    )

    with pytest.raises(FirebaseAuthError, match="stored no session"):
        _snapshot_auth.mint_from_refresh_token("borrowed")
