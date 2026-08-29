"""Mirror the ledger across devices with crdt_sync.

**One CRDT record per ledger entry**, never a single record holding a running
balance. The merge scheme is last-write-wins *per field*, so a `balance` field
would let two devices clobber each other's totals; per-entry records only ever
grow, and the balance is derived from whatever survives the merge.

Two safety properties carried over from the ledger itself:

* **A synced credit still has to prove itself.** Records arriving from another
  device are written into the local ledger, but the integrity table in
  :mod:`leetcode_guard._balance` decides whether they *count* -- an entry whose
  HMAC does not verify against this machine's key is stored and refused. The
  sync repo is a user-writable channel, so without that it would be a way to
  mint credits by committing JSON.
* **Sync never gates unlocking.** Every failure is reported in a
  :class:`SyncResult` and logged; nothing here can keep the lock shut.

The HLC for each record is derived from the entry's own ``created_at`` rather
than from the wall clock, so re-pushing an unchanged ledger produces byte-
identical JSON and no repo churn.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FileSyncStateStore,
    FirebaseAuthError,
    GitHubSyncClient,
    GitHubSyncError,
    LogCodec,
    RemoteStore,
    RemoteSyncError,
    RevisionTracking,
    SyncTarget,
    mirror_client_for,
    sync_log,
)

from leetcode_guard._constants import (
    DEVICE_ID,
    SYNC_PATH_PREFIX,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_STATE_FILE,
    SYNC_TIMEOUT_SECONDS,
    SYNC_TOKEN_FILE,
)
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard._sync_records import (
    decode_log,
    encode_log,
    entries_from_records,
    records_from_ledger,
)
from leetcode_guard._sync_token import read_sync_token

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


_FILENAME: Final = "ledger.json"


def _remote_client(github: RemoteStore) -> RemoteStore:
    """Return the backend to sync against.

    Firebase when ``~/.config/crdt-sync/`` is set up, with GitHub kept as a
    mirror so a device that has not moved yet still converges; GitHub alone
    otherwise. An unconfigured Firebase is a normal state during the cutover,
    not an error.

    The config file is checked *before* constructing anything, so an
    unconfigured machine never reaches the network -- otherwise a test suite
    that blocks real sockets fails here rather than in the code under test.

    Rolling back is deleting this function and passing ``github`` straight
    through: no data moves either way.
    """
    if not CONFIG_FILE.is_file():
        return github
    try:
        return mirror_client_for("leetcode_guard", github)
    except (ConfigError, FirebaseAuthError, RemoteSyncError) as exc:
        # Warning, not info: this repo's no-silent-failures hook is right to
        # insist. A Firebase that quietly stops working would leave the app
        # syncing over the backend being retired, with nothing to say so.
        # Twice a day, so it cannot become journal spam.
        _logger.warning("Firebase unavailable, syncing via GitHub only: %s", exc)
        return github


@dataclass(frozen=True)
class SyncResult:
    """What one sync attempt did.

    A typed result rather than a bare ``bool``/``None``: the repo's
    no-silent-failures rule exists because "it returned False" tells a future
    reader nothing about which of six things went wrong.
    """

    pushed: bool
    record_count: int
    merged_in: int
    reason: str


def sync_ledger(
    ledger_path: Path,
    *,
    token_path: Path | None = None,
    key_file: Path | None = None,
    client: GitHubSyncClient | None = None,
) -> SyncResult:
    """Push our ledger and merge in whatever other devices published.

    Args:
        ledger_path: The local ledger.
        token_path: Where the GitHub token lives. Defaults to the configured
            location, resolved at call time.
        key_file: HMAC key override, for tests.
        client: Pre-built sync client, for tests.

    Returns:
        A result describing exactly what happened. Never raises.
    """
    if client is None:
        token = read_sync_token(SYNC_TOKEN_FILE if token_path is None else token_path)
        if token is None:
            return SyncResult(
                pushed=False,
                record_count=0,
                merged_in=0,
                reason="no sync token configured -- sync is disabled",
            )
        client = GitHubSyncClient(
            SYNC_REPO_OWNER, SYNC_REPO_NAME, token, timeout_seconds=SYNC_TIMEOUT_SECONDS
        )

    ledger = load_ledger(ledger_path, key_file=key_file)
    local = records_from_ledger(ledger)

    try:
        merged = sync_log(
            SyncTarget(
                client=_remote_client(client),
                device_id=DEVICE_ID,
                path_prefix=SYNC_PATH_PREFIX,
            ),
            local,
            LogCodec(
                commit_message="leetcode-guard: update ledger",
                decode=decode_log,
                encode=encode_log,
                filename=_FILENAME,
            ),
            # Without this every tick re-downloads every peer's whole
            # ledger whether or not anything changed -- the traffic the
            # Firebase free tier's monthly budget depends on not happening.
            RevisionTracking(
                state_store=FileSyncStateStore(SYNC_STATE_FILE),
            ),
        )
    except (GitHubSyncError, RemoteSyncError) as exc:
        _logger.warning("ledger sync failed: %s", exc)
        return SyncResult(
            pushed=False,
            record_count=len(local),
            merged_in=0,
            reason=f"sync failed: {exc}",
        )

    added = append(ledger, entries_from_records(merged))
    if added:
        save_ledger(ledger_path, ledger)
        _logger.info("merged %d ledger entries from other devices", added)

    return SyncResult(
        pushed=True,
        record_count=len(merged),
        merged_in=added,
        reason=f"pushed {len(local)} records, merged in {added}",
    )


def sync_quietly(
    ledger_path: Path,
    *,
    token_path: Path | None = None,
    key_file: Path | None = None,
    client: GitHubSyncClient | None = None,
) -> SyncResult:
    """Sync without ever letting a failure escape.

    Used from the lock's close path, where an exception would abort teardown
    and leave the screen grabbed. The parameters are spelled out rather than
    forwarded as ``**kwargs``, so a typo here is a type error rather than a
    silently-ignored argument on the path that matters most.
    """
    try:
        return sync_ledger(
            ledger_path, token_path=token_path, key_file=key_file, client=client
        )
    except Exception:
        _logger.exception("ledger sync raised")
        return SyncResult(
            pushed=False, record_count=0, merged_in=0, reason="sync raised"
        )
