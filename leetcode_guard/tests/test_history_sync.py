"""The ``history:`` line: a per-problem mirror of every submission, with code.

kuhy asked on 2026-11-22 that any Claude coaching a problem see how he tried it,
failed and accepted attempts alike. The one-minute harvester mirrors one slug
per run into ``history/<slug>.json``; display-only, never a gate input.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _harvest_run, _history_store, _history_sync
from leetcode_guard._attempt_store import merge_submissions
from leetcode_guard._constants import EXIT_OK
from leetcode_guard._history_queries import HistoryPage
from leetcode_guard.tests._attempt_helpers import T0
from leetcode_guard.tests._attempt_line_helpers import credit, put_ledger
from leetcode_guard.tests._history_helpers import Remote, codes, mirror, row, run

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_failed_and_an_accepted_attempt_are_mirrored_with_code(hmac_key: Path):
    """The point of the mirror: every status, code included."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    page = HistoryPage((row(2, T0, "Accepted"), row(1, T0 - 50)), has_next=False)

    line = run(Remote({0: page}), hmac_key)

    assert line == "two-sum: 2 submissions, 2 with code"
    assert codes("two-sum") == {"2": "code-2", "1": "code-1"}
    assert mirror("two-sum")["complete"] is True
    statuses = [item["status"] for item in mirror("two-sum")["submissions"]]
    assert statuses == ["Accepted", "Wrong Answer"]


def test_a_ledger_credit_alone_makes_a_slug_due(data_dir: Path, hmac_key: Path):
    """Solves from before attempts.json existed get mirrored too."""
    put_ledger(data_dir, credit("9", "old-solve", T0 - 900, hmac_key))
    remote = Remote({0: HistoryPage((row(9, T0 - 900, "Accepted"),), has_next=False)})

    assert run(remote, hmac_key).startswith("old-solve: 1 submission")
    assert remote.page_calls == [("old-solve", 0)]


def test_could_not_check_writes_nothing(hmac_key: Path):
    """A null payload is silence, never "no submissions"."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)

    assert run(Remote({0: None}), hmac_key) == "two-sum: could not check"
    assert not (_history_store.HISTORY_DIR / "two-sum.json").exists()


def test_code_is_fetched_at_most_five_per_run_and_resumed(hmac_key: Path):
    """The budget bounds the requests a minute; the next run finishes the job."""
    merge_submissions([("7", "two-sum", "Accepted", T0)], now=T0)
    rows = tuple(row(n, T0 - n) for n in range(7, 0, -1))
    remote = Remote({0: HistoryPage(rows, has_next=False)})

    assert run(remote, hmac_key) == "two-sum: 7 submissions, 5 with code"
    assert run(remote, hmac_key) == "two-sum: 7 submissions, 7 with code"
    assert len(remote.code_calls) == len(rows)
    assert remote.page_calls == [("two-sum", 0)]


def test_a_missing_code_answer_leaves_the_row_for_a_later_run(hmac_key: Path):
    """``submissionDetails`` failing costs the code, not the row."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    page = HistoryPage((row(2, T0, "Accepted"),), has_next=False)

    assert (
        run(Remote({0: page}, code={}), hmac_key)
        == "two-sum: 1 submission, 0 with code"
    )
    assert codes("two-sum") == {"2": None}


def test_older_pages_are_walked_one_per_run(hmac_key: Path):
    """``hasNext`` keeps the mirror incomplete until the last page arrives."""
    merge_submissions([("30", "two-sum", "Accepted", T0)], now=T0)
    first = tuple(row(n, T0 - 30 + n) for n in range(30, 10, -1))
    remote = Remote(
        {
            0: HistoryPage(first, has_next=True),
            20: HistoryPage((row(5, T0 - 500),), has_next=False),
        },
        code={},
    )

    run(remote, hmac_key)
    assert mirror("two-sum")["complete"] is False
    run(remote, hmac_key)

    assert remote.page_calls == [("two-sum", 0), ("two-sum", 20)]
    assert mirror("two-sum")["complete"] is True
    assert len(codes("two-sum")) == len(first) + 1


def test_an_up_to_date_mirror_is_idle_and_never_touches_the_network(hmac_key: Path):
    """Nothing newer than the mirror and nothing missing: no request at all."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    remote = Remote({0: HistoryPage((row(2, T0, "Accepted"),), has_next=False)})
    run(remote, hmac_key)

    assert run(remote, hmac_key) == "idle"
    assert len(remote.page_calls) == 1


def test_a_newer_attempt_refetches_the_newest_page(hmac_key: Path):
    """A fresh Wrong Answer on a mirrored problem reaches the mirror."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    old = HistoryPage((row(2, T0, "Accepted"),), has_next=False)
    run(Remote({0: old}), hmac_key)
    merge_submissions([("3", "two-sum", "Wrong Answer", T0 + 100)], now=T0 + 100)
    new = HistoryPage((row(3, T0 + 100), row(2, T0, "Accepted")), has_next=False)

    assert (
        run(Remote({0: new}), hmac_key, at=T0 + 160)
        == "two-sum: 2 submissions, 2 with code"
    )


def test_the_newest_activity_goes_first(hmac_key: Path):
    """One slug per run, the one he touched last."""
    merge_submissions([("1", "older", "Accepted", T0 - 600)], now=T0)
    merge_submissions([("2", "newer", "Wrong Answer", T0)], now=T0)
    remote = Remote({0: HistoryPage((), has_next=False)})

    run(remote, hmac_key)

    assert remote.page_calls == [("newer", 0)]


def test_main_prints_the_history_line_last(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], hmac_key: Path
):
    """The harvester runs it after the attempts line, every run."""
    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_: "harvest ok")
    monkeypatch.setattr(_history_sync, "history_line", lambda **_: "idle")

    assert _harvest_run.main(key_file=hmac_key) == EXIT_OK

    assert capsys.readouterr().out.splitlines()[-1] == "history: idle"


def test_main_survives_a_history_line_that_raises(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    hmac_key: Path,
):
    """A bug in the mirror costs the line, never the exit code."""

    def explode(**_: object) -> str:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_: "harvest ok")
    monkeypatch.setattr(_history_sync, "history_line", explode)

    with caplog.at_level(logging.WARNING):
        assert _harvest_run.main(key_file=hmac_key) == EXIT_OK

    assert "history: unavailable (RuntimeError)" in capsys.readouterr().out
    assert "history line unavailable" in caplog.text
