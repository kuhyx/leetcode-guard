"""Assertions shared by the ``test_cli*`` modules."""

from __future__ import annotations

import pytest

from leetcode_guard import _cli


def assert_production_exits_unarmed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--production`` on a settled day exits 0 without building the lock.

    Args:
        monkeypatch: Used to make arming the lock fail the test.
        capsys: Reads what the command printed.
    """
    monkeypatch.setattr(
        _cli, "LeetcodeGuard", lambda **kwargs: pytest.fail("should not have armed")
    )

    assert _cli.main(["--production"]) == 0
    assert "already unlocked" in capsys.readouterr().out
