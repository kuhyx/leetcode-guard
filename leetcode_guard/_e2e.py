"""End-to-end encryption of everything leetcode-guard puts in a sync backend.

Every payload is sealed with a key derived (Argon2id) from the shared
crdt-sync passphrase, so RTDB and the GitHub mirror only ever hold ciphertext.
Three groups, each a NEW ``-e2e`` prefix (the old one is never deleted here):

* the ledger log, ``leetcode-guard-sync/devices-e2e`` (``_sync``), copied
  once from the old prefix by crdt_sync's ``open_encrypted_client``;
* the snapshot leaves, ``leetcode-guard/snapshot-e2e/{status,status_hash,
  heartbeat}`` (``_snapshot_push``, read by the phone);
* the phone's error reports, ``leetcode-guard/app_errors-e2e/<device>``
  (written by the phone, read by ``_phone_errors_sync``).

The last two share one header, ``leetcode-guard/e2e``, so one Argon2 run
opens both. Their old nodes are not crdt logs, so there is nothing to copy:
the snapshot is rewritten within a minute and a delivered error was already
announced. ``leetcode-guard/coach`` stays clear: utils' leetcode_coach relay
reads it too and moves with that repo, never alone.

**Locked fails closed.** No passphrase, a wrong one or an unreadable header
raises ``E2eLockedError``; callers skip the tick, never write plaintext.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from crdt_sync import PASSWORD_FILE, E2eLayout, EncryptingStore, open_encrypted_client

from leetcode_guard._constants import DATA_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync import Argon2Params, E2eKey, RemoteStore

_logger: Final = logging.getLogger(__name__)

SNAPSHOT_OLD_PREFIX: Final = "leetcode-guard/snapshot"

SNAPSHOT_LAYOUT: Final = E2eLayout.of(SNAPSHOT_OLD_PREFIX)
"""``leetcode-guard/snapshot`` never existed: an empty old tree to copy from."""

APP_ERRORS_LAYOUT: Final = E2eLayout.of("leetcode-guard/app_errors")

PASSWORD_PATH: Path = PASSWORD_FILE
"""The shared crdt-sync passphrase. Module state so tests can redirect it."""

STATE_DIR: Path = DATA_DIR / "e2e"
"""The derived keys (0600) and copy memos, so the per-minute harvester runs
Argon2 once, not every minute. Module state so tests can redirect it."""

PARAMS: Argon2Params | None = None
"""Argon2 cost for a header this device creates; ``None`` is the library's
recommended cost. Tests lower it."""


def read_passphrase() -> str:
    """The shared passphrase, or ``""`` (locked) when it cannot be read."""
    try:
        return PASSWORD_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _logger.warning("crdt-sync passphrase unreadable: %s", type(exc).__name__)
        return ""


def unlock_shared(client: RemoteStore) -> E2eKey:
    """The key behind ``leetcode-guard/e2e``, creating the header on first use.

    The key is cached in :data:`STATE_DIR` and checked against the header;
    the old tree (``leetcode-guard/snapshot``) never existed, so the one-time
    copy finds nothing and its memo ends the listing after the first run.

    Raises:
        E2eLockedError: No passphrase, a wrong one, or an unreadable header.
    """
    store, _ = open_encrypted_client(
        client,
        SNAPSHOT_OLD_PREFIX,
        passphrase=read_passphrase(),
        params=PARAMS,
        state_dir=STATE_DIR,
    )
    return store.key


def sealed(inner: RemoteStore, key: E2eKey, layout: E2eLayout) -> EncryptingStore:
    """``inner`` sealing every path under ``layout``'s prefix."""
    return EncryptingStore(inner, key, layout)
