"""The gate does not re-arm after tonight's evening night-lockdown."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli, _cli_commands, _night_lockdown
from leetcode_guard._night_lockdown import defer_for_evening_lockdown
from leetcode_guard.tests._net_fixtures import pool_result, recent_ac_result
from leetcode_guard.tests.test_cli import (
    _seeded_ledger,
    patch_cli,
    stub_client,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 17, 22, 30).astimezone()


def _stamp(when: str) -> None:
    """Write the redirected stamp for a LOCAL wall-clock time."""
    epoch = int(datetime.fromisoformat(when).astimezone().timestamp())
    _night_lockdown.NIGHT_LOCKDOWN_STAMP.write_text(f"{epoch}\n")


def test_the_stamp_is_redirected_off_the_real_one(data_dir: Path) -> None:
    assert data_dir / "locked_at_epoch" == _night_lockdown.NIGHT_LOCKDOWN_STAMP


def test_missing_stamp_does_not_defer() -> None:
    assert defer_for_evening_lockdown(NOW) is None


def test_tonights_evening_lockdown_defers() -> None:
    _stamp("2026-10-17T21:05")
    assert defer_for_evening_lockdown(NOW) == (
        "night lockdown already locked tonight at 21:05; the gate does not "
        "re-arm after it"
    )


def test_the_0401_morning_relock_does_not_defer() -> None:
    _stamp("2026-10-17T04:01")
    assert defer_for_evening_lockdown(NOW) is None


def test_yesterdays_evening_lockdown_does_not_defer() -> None:
    _stamp("2026-10-16T21:05")
    assert defer_for_evening_lockdown(NOW) is None


def test_garbage_stamp_does_not_defer(caplog: pytest.LogCaptureFixture) -> None:
    _night_lockdown.NIGHT_LOCKDOWN_STAMP.write_text("garbage")
    assert defer_for_evening_lockdown(NOW) is None
    assert "not a unix epoch" in caplog.text


class _FakeGuard:
    built = False

    def __init__(self, **kwargs: object) -> None:
        type(self).built = True

    def run(self) -> None:
        pass


@pytest.fixture
def armable(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> type[_FakeGuard]:
    """A production run that would arm: seeded ledger, nothing solved today."""
    _FakeGuard.built = False
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    patch_cli(monkeypatch, "LeetcodeGuard", _FakeGuard)
    _seeded_ledger(data_dir)
    return _FakeGuard


def test_production_does_not_arm_after_tonights_lockdown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    armable: type[_FakeGuard],
) -> None:
    seen: list[datetime] = []

    def _defer(now: datetime) -> str:
        seen.append(now)
        return "night lockdown already locked tonight at 21:05"

    patch_cli(monkeypatch, "defer_for_evening_lockdown", _defer)
    assert _cli.main(["--production"]) == 0
    assert not armable.built
    assert "deferred: night lockdown already locked tonight at 21:05" in (
        capsys.readouterr().out
    )
    assert len(seen) == 1


def test_production_after_the_morning_relock_still_arms(
    armable: type[_FakeGuard],
) -> None:
    _stamp(f"{datetime.now(tz=UTC).astimezone():%Y-%m-%d}T04:01")
    assert _cli.main(["--production"]) == 0
    assert armable.built


def test_demo_ignores_tonights_lockdown(
    monkeypatch: pytest.MonkeyPatch, armable: type[_FakeGuard]
) -> None:
    patch_cli(
        monkeypatch,
        "defer_for_evening_lockdown",
        lambda now: pytest.fail("demo must not consult the night lockdown"),
    )
    assert _cli.main([]) == 0
    assert armable.built


def test_check_reports_tonights_lockdown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        _cli_commands, "defer_for_evening_lockdown", lambda now: "locked at 21:05"
    )
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    _cli_commands.cmd_check()
    assert "evening    locked at 21:05" in capsys.readouterr().out


def test_check_reports_no_lockdown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    _cli_commands.cmd_check()
    assert "evening    no lockdown yet tonight" in capsys.readouterr().out
