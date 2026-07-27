"""Suite-wide safety rails.

Two autouse fixtures, both of which exist because the failure they prevent is
silent rather than loud:

* real network calls are blocked, so a test that forgets to inject a fake fails
  fast instead of quietly depending on leetcode.com being up;
* every configured path is redirected into ``tmp_path``, so no test can read or
  write the real ledger, cache or cookie file.

The Tk-blocking fixture lands here in Phase 3, before any window module exists.
"""

from __future__ import annotations

from datetime import date
import importlib
import sys
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import requests

import leetcode_guard._leetcode as leetcode_module

if TYPE_CHECKING:
    from pathlib import Path


class _BlockedSession:
    """Stands in for :class:`requests.Session` and refuses to do anything."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()

    def post(self, *args: object, **kwargs: object) -> object:
        message = (
            "a test tried to reach the network; inject a fake PostFn "
            "(see leetcode_guard.tests._net_fixtures)"
        )
        raise AssertionError(message)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make real HTTP impossible for the whole suite."""
    monkeypatch.setattr(leetcode_module.requests, "Session", _BlockedSession)


_TK_MODULES = (
    "leetcode_guard._view",
    "leetcode_guard._escape_flow",
    "leetcode_guard._lock",
    "leetcode_guard._status_sections",
    "leetcode_guard.status_view",
)
"""Every module that does ``import tkinter as tk``.

Any new one must be added here **in the same commit**. Miss one and the suite
does not fail -- it opens a real fullscreen window, or worse, hangs holding a
grab.
"""


@pytest.fixture(autouse=True)
def _block_real_tk(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Make it impossible for a test to open a real window or grab input.

    The whole ``tk`` *module* reference is replaced, not just ``tk.Tk``, so a
    test that forgets to request a mock cannot reach tkinter by any route.
    ``tk.TclError`` is preserved as the real class so ``except tk.TclError``
    still behaves.
    """
    fake = MagicMock()
    fake.TclError = tk.TclError
    for name in _TK_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "tk", fake, raising=True)

    import leetcode_guard._lock as lock_module

    monkeypatch.setattr(lock_module, "GateRoot", MagicMock(), raising=True)
    monkeypatch.setattr(
        lock_module, "assert_not_under_pytest", lambda _what: None, raising=True
    )
    return fake


@pytest.fixture(autouse=True)
def _gate_in_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the gate active for every test by default.

    ``GATE_START_DATE`` is a real future date, so without this every scenario
    would return ``UNLOCKED_NOT_STARTED`` and quietly stop testing anything the
    day it was introduced. Tests that are *about* the start date patch it back
    to a value they choose.
    """
    past = date(2000, 1, 1)
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("leetcode_guard.") and hasattr(
            module, "GATE_START_DATE"
        ):
            monkeypatch.setattr(module, "GATE_START_DATE", past, raising=True)


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
        "STATEMENTS_CACHE_FILE": data / "statements_cache.json",
        "ESCAPE_HISTORY_FILE": data / "escape_history.json",
        "DEMO_ESCAPE_HISTORY_FILE": data / "escape_history_demo.json",
        "NETWORK_INCIDENTS_FILE": data / "network_incidents.json",
        "DEMO_NETWORK_INCIDENTS_FILE": data / "network_incidents_demo.json",
        "USERNAME_FILE": config / "username",
        "COOKIES_FILE": config / "cookies.json",
        "SYNC_TOKEN_FILE": config / "sync_token",
        "INSTANCE_LOCK_FILE": data / "instance.lock",
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


@pytest.fixture
def hmac_key(tmp_path: Path) -> Path:
    """A real 32-byte signing key, isolated per test.

    Every ledger test passes this explicitly, so nothing in the suite ever
    signs or verifies against ``/etc/workout-locker/hmac.key``. That keeps the
    tests independent of a root-owned file *and* stops them producing entries
    that would verify against the live production key.
    """
    from leetcode_guard.tests._ledger_fixtures import make_hmac_key

    return make_hmac_key(tmp_path)


@pytest.fixture
def missing_key(tmp_path: Path) -> Path:
    """A key path that does not exist -- the integrity-OFF branch."""
    return tmp_path / "absent" / "hmac.key"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """The isolated config directory created by :func:`_isolate_paths`."""
    return tmp_path / "config"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """The isolated data directory created by :func:`_isolate_paths`."""
    return tmp_path / "data"


@pytest.fixture
def gate_starts(monkeypatch: pytest.MonkeyPatch):
    """Re-arm the real start date for tests that are about it.

    Counterpart to ``_gate_in_force``, which switches it off everywhere else.
    """
    from leetcode_guard import _constants, _gate

    monkeypatch.setattr(_gate, "GATE_START_DATE", _constants.GATE_START_DATE)
    return _constants.GATE_START_DATE


@pytest.fixture
def tk_mock(_block_real_tk: MagicMock) -> MagicMock:
    """Public alias for the Tk stand-in.

    ``_block_real_tk`` is autouse and underscore-prefixed, which the lint
    profile rightly objects to as a *requested* parameter. Tests that need to
    inspect what was asked of Tk take this instead.
    """
    return _block_real_tk
