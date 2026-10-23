"""The harvester must start and harvest whatever the snapshot code does.

``_harvest_run`` mints credits; the snapshot push is display-only. A crdt_sync
that lost a name only the snapshot uses (a sibling repo's install bumping the
shared user site), an import error in a snapshot module, or a push that
raises must cost at most the push -- never the harvest, never the start.

Measured 2026-10-23: crdt_sync *as a whole* cannot be optional here. The gate
itself imports ``freedays`` and ``sickdays``, and both import crdt_sync at
module level, so a crdt_sync that fails to import at all stops the gate
before any snapshot code is reached. What this file pins is that the
snapshot adds no import-time dependency of its own.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from leetcode_guard import _harvest_run, _snapshot_push
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._net_fixtures import recent_ac_result, submission_row
from leetcode_guard.tests.test_harvest_run import seeded_ledger, stub_client

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SNAPSHOT_MODULES = (
    "leetcode_guard._snapshot_push",
    "leetcode_guard._snapshot_auth",
    "leetcode_guard._snapshot_rtdb",
)


def test_starting_the_harvester_loads_no_snapshot_code():
    """A fresh interpreter, so no earlier import can mask the dependency."""
    probe = (
        "import sys; import leetcode_guard._harvest_run; "
        "loaded = sorted(m for m in sys.modules if m.startswith(("
        "'leetcode_guard._snapshot', 'leetcode_guard._profile', "
        "'leetcode_guard._coach'))); "
        "print(loaded)"
    )
    root = __file__.rsplit("/leetcode_guard/", 1)[0]

    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def _a_fresh_solve(monkeypatch: pytest.MonkeyPatch, data_dir: Path, key: Path) -> Path:
    path = data_dir / "ledger.json"
    seeded_ledger(path, key)
    stub_client(monkeypatch, recent_ac_result([submission_row("9", "two-sum")]))
    return path


def test_a_harvest_still_credits_with_crdt_sync_unimportable(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    hmac_key: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
):
    path = _a_fresh_solve(monkeypatch, data_dir, hmac_key)
    monkeypatch.setitem(sys.modules, "crdt_sync", None)
    for name in SNAPSHOT_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)

    assert _harvest_run.main(key_file=hmac_key) == 0

    out = capsys.readouterr().out
    assert "credited 1" in out
    assert "snapshot: push unavailable" in out
    assert "snapshot push unavailable" in caplog.text
    assert any(
        e.startswith("ac:") for e in load_ledger(path, key_file=hmac_key).entries
    )


def test_a_harvest_still_credits_when_the_push_raises(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    hmac_key: Path,
    capsys: pytest.CaptureFixture[str],
):
    _a_fresh_solve(monkeypatch, data_dir, hmac_key)

    def explode() -> object:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(_snapshot_push, "push_quietly", explode)

    assert _harvest_run.main(key_file=hmac_key) == 0
    out = capsys.readouterr().out
    assert "credited 1" in out
    assert "snapshot: push unavailable" in out
