"""C6 is fenced inside the theory poll: a trigger bug never costs a credit."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _theory_credit
from leetcode_guard._ledger_io import Ledger
from leetcode_guard.tests import _theory_scenario as scene
from leetcode_guard.tests._finish_fixtures import A_ID, NOW, TODAY, flips, ids, poll

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _boom(*_a: object, **_k: object) -> list[object]:
    raise RuntimeError


def test_a_raising_trigger_never_costs_the_polls_credit(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """C6 is fenced on its own: the finish credit still mints, one warning."""
    monkeypatch.setattr(_theory_credit, "record_finishes", _boom)
    scene.world(tmp_path, monkeypatch)
    scene.began(hmac_key)
    scene.taught(hmac_key, NOW, ("a", 9))
    flips(hmac_key, ("a", True, TODAY))

    with caplog.at_level(logging.WARNING):
        result = poll(Ledger(), data_dir, hmac_key)

    assert ids(result) == [A_ID]
    assert "unit finish not recorded: RuntimeError" in caplog.text
