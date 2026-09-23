"""The path redirect, as a pytest plugin.

Split from ``conftest.py`` for the file-length cap when ``PROGRESS_CACHE_FILE``
was added. Every configured on-disk path is redirected into ``tmp_path`` so no
test can read or write the real ledger, cache or cookie file. A new path
constant goes into ``overrides`` **in the same edit** that adds it -- on
2026-08-24 a moved constant left the redirect pointing at the old module and
the suite wrote 27 fake entries into the live audit log while staying green.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every configured path at a per-test directory.

    Patched at each *importing* module rather than only at ``_constants``:
    ``from ... import X`` binds a new name, so rebinding the original leaves
    every consumer still pointing at the real file.
    """
    config = tmp_path / "config"
    data = tmp_path / "data"
    config.mkdir()
    data.mkdir()

    from leetcode_guard import _constants

    overrides = {
        "CONFIG_DIR": config,
        "DATA_DIR": data,
        "LEDGER_FILE": data / "ledger.json",
        "DEMO_LEDGER_FILE": data / "ledger_demo.json",
        "POOL_CACHE_FILE": data / "pool_cache.json",
        "PROGRESS_CACHE_FILE": data / "progress_cache.json",
        "STATEMENTS_CACHE_FILE": data / "statements_cache.json",
        "ESCAPE_HISTORY_FILE": data / "escape_history.json",
        "DEMO_ESCAPE_HISTORY_FILE": data / "escape_history_demo.json",
        "NETWORK_INCIDENTS_FILE": data / "network_incidents.json",
        "DEMO_NETWORK_INCIDENTS_FILE": data / "network_incidents_demo.json",
        "USERNAME_FILE": config / "username",
        "COOKIES_FILE": config / "cookies.json",
        "SYNC_TOKEN_FILE": config / "sync_token",
        "INSTANCE_LOCK_FILE": data / "instance.lock",
        # Added with the Firebase cutover. Redirected for the same reason as
        # everything above: a test must not read or write the developer's own
        # sync state.
        "SYNC_STATE_FILE": data / "sync_state.json",
        # The morning-session carrot: a test must never defer on the
        # developer's real morning.
        "MORNING_SESSION_FILE": data / "morning_session.json",
        # The workday-stick penalty: a test must never price a day off the
        # developer's real penalty state.
        "WORKDAY_PENALTY_FILE": data / "workday_penalty.json",
    }
    for name, value in overrides.items():
        monkeypatch.setattr(_constants, name, value, raising=True)

    # Every already-imported module that pulled a path constant in by value
    # gets its own copy rebound. Enumerating modules by hand was the version of
    # this that went wrong: adding _status.py silently left it reading the real
    # ~/.local/share directory, because nothing failed -- the tests just quietly
    # started depending on the developer's own ledger.
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("leetcode_guard."):
            continue
        for name, value in overrides.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value, raising=True)
