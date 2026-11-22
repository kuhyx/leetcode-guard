"""The lock is never swapped: unit directive, live cgroup, deploy health.

2026-11-22: the idle lock had 57 MB in swap, and with zram full its Tk ticks
waited on disk swap-in for up to 1.7 s (perf.slow ``tk.mainloop``, c890f31a).
``MemorySwapMax=0`` keeps the lock's anon pages in RAM. Deploy never restarts
the lock, so it also applies the limit to a running one and checks it took.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard.tests._deploy_fixtures import REPO, Env, make_sandbox, run_deploy

if TYPE_CHECKING:
    from pathlib import Path

UNIT = REPO / "leetcode-guard.service"
SET_PROPERTY = (
    "systemctl --user set-property --runtime leetcode-guard.service MemorySwapMax=0"
)


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path: Path) -> Env:
    """A bare origin, a clean live clone of it, and the fakes."""
    return make_sandbox(tmp_path)


def test_the_unit_pins_the_lock_out_of_swap() -> None:
    """The directive is in [Service], not a comment."""
    service = (
        UNIT.read_text(encoding="utf-8").split("[Service]")[1].split("[Install]")[0]
    )
    directives = [line.strip() for line in service.splitlines()]
    assert "MemorySwapMax=0" in directives


def test_a_running_lock_gets_the_limit_without_a_restart(sandbox: Env) -> None:
    """set-property applies to the live cgroup; the lock window stays up."""
    proc = run_deploy(sandbox)
    assert proc.returncode == 0, proc.stderr
    calls = sandbox.log.read_text(encoding="utf-8")
    assert SET_PROPERTY in calls
    assert "ok: lock is out of swap" in proc.stderr


def test_a_settled_day_has_no_lock_to_limit(sandbox: Env) -> None:
    """No running lock: nothing to set, nothing to read, deploy still passes."""
    proc = run_deploy(sandbox, FAKE_DEAD="leetcode-guard.service")
    assert proc.returncode == 0, proc.stderr
    assert SET_PROPERTY not in sandbox.log.read_text(encoding="utf-8")


def test_a_unit_without_the_directive_fails_health(sandbox: Env) -> None:
    """An installed unit that lost the line is named, lock up or not."""
    proc = run_deploy(
        sandbox, FAKE_SWAP_MAX="infinity", FAKE_DEAD="leetcode-guard.service"
    )
    assert proc.returncode != 0
    assert "MemorySwapMax" in proc.stderr


def test_a_live_cgroup_still_swapping_fails_health(
    sandbox: Env, tmp_path: Path
) -> None:
    """set-property that did not reach the cgroup is a failed deploy."""
    (tmp_path / "cgroup" / "lock" / "memory.swap.max").write_text(
        "max\n", encoding="utf-8"
    )
    proc = run_deploy(sandbox)
    assert proc.returncode != 0
    assert "memory.swap.max" in proc.stderr
