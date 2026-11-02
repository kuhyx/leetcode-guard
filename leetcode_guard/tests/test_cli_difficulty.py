"""``--backfill-difficulty`` resolves, reports and writes only the cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _cli, _cli_difficulty, _constants
from leetcode_guard._auth import AuthState
from leetcode_guard._difficulty import load_weights
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._settings import Client
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, submission
from leetcode_guard.tests._net_fixtures import fake_post

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_backfill_resolves_reports_and_leaves_the_ledger_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], hmac_key: Path
):
    ledger = Ledger()
    append(
        ledger,
        [
            credit_entry(
                submission(str(i), slug), day=MONDAY, now=NOW, key_file=hmac_key
            )
            for i, slug in enumerate(["a", "b", "c"])
        ],
    )
    save_ledger(_constants.LEDGER_FILE, ledger)
    before = _constants.LEDGER_FILE.read_text(encoding="utf-8")
    post = fake_post(GraphQLResult(data={"question": {"difficulty": "Hard"}}))
    monkeypatch.setattr(
        _cli_difficulty,
        "build_client",
        lambda: Client(post=post, auth=AuthState(cookies=None, note=""), username="k"),
    )

    assert _cli.main(["--backfill-difficulty", "--max-fetch", "2"]) == 0

    out = capsys.readouterr().out
    assert (
        "3 credited problems: 0 already known, 2 resolved now (2 from LeetCode)" in out
    )
    assert "1 deferred" in out
    assert "unknown    1" in out
    assert load_weights().weight("a") == 4
    assert _constants.LEDGER_FILE.read_text(encoding="utf-8") == before
