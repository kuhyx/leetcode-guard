"""Night lockdown: the X server is gone, the lock run is waiting for it.

The deadlock found 2026-10-17. Lockdown stops lightdm, so ``:0`` dies while the
user manager lingers; an unsettled day's ``leetcode-guard.service`` exits 1 and
is restarted, and the restarted ``cmd_lock`` used to take the instance lock
*before* waiting -- forever -- for X. The one-minute harvest saw the lock held
and stood aside, so no solve could be credited, and X comes back only once a
credit lands. A run that is still waiting for a display holds nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli, _harvest_run
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._net_fixtures import recent_ac_result, submission_row
from leetcode_guard.tests.test_harvest_run import seeded_ledger, stub_client

if TYPE_CHECKING:
    from pathlib import Path


class _XNeverCameBackError(Exception):
    """End the otherwise unbounded X wait once the harvest has had its turn."""


def test_a_solve_during_lockdown_is_credited_while_the_lock_waits_for_x(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """X absent, lock run waiting: the harvest must still credit the solve."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(
        _cli, "build_client", lambda: pytest.fail("no X: must not reach LeetCode")
    )

    def harvest_tick_during_the_wait() -> bool:
        _harvest_run.main(key_file=hmac_key)
        raise _XNeverCameBackError

    monkeypatch.setattr(_cli, "wait_for_x_server", harvest_tick_during_the_wait)

    with pytest.raises(_XNeverCameBackError):
        _cli.main(["--production"])

    assert "credited 1" in capsys.readouterr().out
    assert load_ledger(data_dir / "ledger.json").has("ac:42")


def test_the_instance_lock_is_taken_only_once_x_answers(monkeypatch, data_dir):
    """Still single-instance: the lock is acquired, just after the display."""
    order: list[str] = []
    monkeypatch.setattr(_cli, "wait_for_x_server", lambda: order.append("x"))

    def stand_down(_path: Path) -> None:
        order.append("instance")

    monkeypatch.setattr(_cli, "acquire_instance", stand_down)

    assert _cli.main(["--production"]) == 0
    assert order == ["x", "instance"]
