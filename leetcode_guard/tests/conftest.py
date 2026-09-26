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
from leetcode_guard.tests._tk_stub import TK_MODULES, fake_gatelock_widgets

if TYPE_CHECKING:
    from pathlib import Path


class _BlockedSession:
    """Stands in for :class:`requests.Session` and refuses to do anything."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()

    def mount(self, *args: object, **kwargs: object) -> None:
        """Accept adapter registration without doing anything.

        ``crdt_sync._http`` mounts a retry adapter while *building* a session,
        long before any request is made. Refusing here would fail at import
        time, which is not what this stub is for -- the refusal belongs in
        :meth:`post`, where a test actually tries to reach the network.
        """

    def post(self, *args: object, **kwargs: object) -> object:
        message = (
            "a test tried to reach the network; inject a fake PostFn "
            "(see leetcode_guard.tests._net_fixtures)"
        )
        raise AssertionError(message)


pytest_plugins = [
    "leetcode_guard.tests._debt_fixtures",
    "leetcode_guard.tests._paths_fixture",
]


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make real HTTP impossible for the whole suite."""
    monkeypatch.setattr(leetcode_module.requests, "Session", _BlockedSession)


@pytest.fixture(autouse=True)
def _no_live_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the status surfaces' one network call to "nothing known".

    The window starts it on a worker thread, where the network rail above
    would only surface as a logged exception; ``--sync`` and ``--status --by``
    make it inline. Tests about the fetch itself rebind these explicitly.
    """
    import leetcode_guard._cli_commands as cli_commands
    import leetcode_guard._status_fetch as status_fetch

    for module in (cli_commands, status_fetch):
        monkeypatch.setattr(module, "fetch_live_progress", lambda: None)


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
    for name in TK_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "tk", fake, raising=True)
    fake_gatelock_widgets(monkeypatch, fake)

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
def _no_morning_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the morning-session reader sleep in a test.

    Its file is redirected by ``_isolate_paths``; this is the other half --
    on the enforce path a missing file inside 07:00-11:00 is retried for 30
    real seconds, which a test running in that window would silently pay.
    """
    from leetcode_guard import _morning_session

    monkeypatch.setattr(_morning_session, "MORNING_RETRY_SECONDS", 0.0, raising=True)


@pytest.fixture(autouse=True)
def _no_free_days_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never let the gate read the developer's real free-day pool.

    Same reason as ``_isolate_paths``: the pool lives under ``~/.local/share``
    and a real free day would silently unlock every gate scenario in this
    suite. Tests that are *about* free days mark one into this redirected
    pool.
    """
    import freedays._api

    # Built once: the projection tests ask is_free_day about ~700k days, and
    # rebuilding this (frozen, side-effect-free) bundle per call was a large
    # share of the suite's CI time.
    isolated = freedays.Paths.under(tmp_path / "freedays")
    monkeypatch.setattr(freedays._api, "resolve_paths", lambda paths: paths or isolated)


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
def no_spawn(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A browser that always resolves and never actually runs.

    Here rather than in a test module because two split halves of the study
    suite request it by name, and a fixture imported across modules reads as
    an unused import to the linter, which removes it.
    """
    launched: list[str] = []
    monkeypatch.setattr(
        "leetcode_guard._lock_study.find_opener", lambda: "/usr/bin/xdg-open"
    )

    def fake_launch(url: str) -> MagicMock:
        launched.append(url)
        return MagicMock(ok=True, reason="opened", command=())

    monkeypatch.setattr("leetcode_guard._lock_study.launch", fake_launch)
    return launched


@pytest.fixture
def tk_mock(_block_real_tk: MagicMock) -> MagicMock:
    """Public alias for the Tk stand-in.

    ``_block_real_tk`` is autouse and underscore-prefixed, which the lint
    profile rightly objects to as a *requested* parameter. Tests that need to
    inspect what was asked of Tk take this instead.
    """
    return _block_real_tk
