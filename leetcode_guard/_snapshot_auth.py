"""Sign the snapshot pusher into Firebase, healing from a sibling app's session.

crdt_sync caches a refresh token per app and falls back to the shared
password only when that cache is missing. Measured 2026-10-23: that password
answers ``INVALID_LOGIN_CREDENTIALS``, while a dozen sibling apps under
``~/.config`` hold live refresh tokens for the same account and project. So a
missing or revoked session is rebuilt from a sibling's token -- the pattern
``screen_locker/_credential_recovery.py`` established on 2026-08-24,
duplicated here in a few lines rather than imported across repos.

Only crdt_sync's public API is used: the borrowed token is exchanged by a
:class:`FirebaseTokenProvider` holding it as already expired, which is the
library's own refresh path. A sibling's cache is read, never written.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FileCredentialStore,
    FirebaseAuthError,
    FirebaseConfig,
    FirebaseCredentials,
    FirebaseTokenProvider,
    MemoryCredentialStore,
    firebase_client_for,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import RemoteStore

_logger: Final = logging.getLogger(__name__)

CONFIG_ROOT: Final = Path.home() / ".config"
"""Where crdt_sync keeps every app's ``<app>/firebase_auth.json``."""

CACHE_NAME: Final = "firebase_auth.json"

_LONG_AGO: Final = datetime(1970, 1, 1, tzinfo=UTC)


def mint_from_refresh_token(refresh_token: str) -> FirebaseCredentials:
    """Exchange a borrowed refresh token for a session of our own.

    Raises:
        ConfigError: If the shared config is unusable.
        FirebaseAuthError: If the token is rejected.
    """
    config = FirebaseConfig.load(CONFIG_FILE)
    store = MemoryCredentialStore(
        FirebaseCredentials(
            id_token="", refresh_token=refresh_token, expires_at=_LONG_AGO
        )
    )
    FirebaseTokenProvider(config.api_key, store).id_token()
    fresh = store.load()
    if fresh is None:
        message = "the token provider stored no session after refreshing"
        raise FirebaseAuthError(message)
    return fresh


def _sibling_caches(config_root: Path, *, skip: str) -> list[Path]:
    """Every other app's cache, most recently refreshed first."""
    caches = [
        path for path in config_root.glob(f"*/{CACHE_NAME}") if path.parent.name != skip
    ]
    return sorted(caches, key=lambda path: path.stat().st_mtime, reverse=True)


def adopt_sibling_session(
    app_name: str,
    *,
    config_root: Path,
    mint: Callable[[str], FirebaseCredentials],
) -> str | None:
    """Seed ``app_name``'s cache from the first sibling whose token still works.

    Returns:
        The donor app's name, or ``None`` when no sibling could help.
    """
    for cache in _sibling_caches(config_root, skip=app_name):
        borrowed = FileCredentialStore(cache).load()
        if borrowed is None:
            continue
        try:
            fresh = mint(borrowed.refresh_token)
        except FirebaseAuthError as exc:
            # A stale donor says nothing about the next one; keep looking.
            _logger.warning(
                "%s's refresh token was rejected: %s", cache.parent.name, exc
            )
            continue
        FileCredentialStore(config_root / app_name / CACHE_NAME).save(fresh)
        return cache.parent.name
    return None


def connect(
    app_name: str,
    *,
    timeout_seconds: float,
    client_for: Callable[..., RemoteStore] | None = None,
    config_root: Path | None = None,
    mint: Callable[[str], FirebaseCredentials] | None = None,
) -> RemoteStore:
    """A signed-in RTDB client for ``app_name``, healing a dead session once.

    Raises:
        ConfigError: If the shared config is unusable.
        FirebaseAuthError: If neither our session nor any sibling's works.
    """
    build = firebase_client_for if client_for is None else client_for
    try:
        return build(app_name, timeout_seconds=timeout_seconds)
    except (ConfigError, FirebaseAuthError) as exc:
        _logger.warning(
            "no Firebase session for %s (%s); borrowing a sibling app's", app_name, exc
        )
    root = CONFIG_ROOT if config_root is None else config_root
    donor = adopt_sibling_session(
        app_name,
        config_root=root,
        mint=mint_from_refresh_token if mint is None else mint,
    )
    if donor is None:
        message = f"no sibling app under {root} holds a live Firebase session"
        raise FirebaseAuthError(message)
    _logger.warning(
        "rebuilt the Firebase session for %s from %s's cache", app_name, donor
    )
    return build(app_name, timeout_seconds=timeout_seconds)
