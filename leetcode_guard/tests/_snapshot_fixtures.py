"""Suite-wide rails for the status-app snapshot, as a pytest plugin.

A plugin rather than more ``conftest.py`` for the line cap, and separate from
``_paths_fixture`` because that one applies every override to ``_constants``
with ``raising=True`` -- and these paths live in the modules that own them,
since ``_constants`` is at the cap.

All of it is fail-closed for the same reason as the network rail: once
``save_ledger`` requests a push and every harvest publishes, a test that
forgot to stub either would spawn a real process or write the real RTDB node
while staying green.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _refuse_firebase(*_args: object, **_kwargs: object) -> object:
    message = (
        "a test tried to reach Firebase; pass connect= to push_snapshot "
        "(see leetcode_guard.tests.test_snapshot_push)"
    )
    raise AssertionError(message)


@pytest.fixture(autouse=True)
def _isolate_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[list[str]]:
    """Redirect the snapshot's own files and block both of its side effects."""
    from leetcode_guard import (
        _coach_log,
        _profile_cache,
        _push_trigger,
        _snapshot_auth,
        _snapshot_dedup,
        _snapshot_local,
        _snapshot_push,
    )

    spawned: list[list[str]] = []
    monkeypatch.setattr(_push_trigger, "_spawn", spawned.append)
    monkeypatch.setattr(_snapshot_auth, "firebase_client_for", _refuse_firebase)
    monkeypatch.setattr(_snapshot_auth, "CONFIG_ROOT", tmp_path / "config-root")
    monkeypatch.setattr(
        _snapshot_push,
        "push_quietly",
        lambda: _snapshot_push.PushResult(
            pushed=False, reason="push stubbed in tests", size=0
        ),
    )
    monkeypatch.setattr(
        _profile_cache, "PROFILE_CACHE_FILE", tmp_path / "data" / "profile_cache.json"
    )
    monkeypatch.setattr(
        _snapshot_dedup, "PUSH_STATE_FILE", tmp_path / "data" / "push_state.json"
    )
    monkeypatch.setattr(
        _snapshot_local, "LOCAL_SNAPSHOT_FILE", tmp_path / "data" / "snapshot.json"
    )
    monkeypatch.setattr(
        _coach_log, "COACH_SESSIONS_DIR", tmp_path / "coach" / "sessions"
    )
    return spawned
