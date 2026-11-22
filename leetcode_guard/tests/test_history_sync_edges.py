"""The ``history:`` line's edges: paging, bursts, bad slugs, failing code, wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from leetcode_guard import _history_store, _history_sync
from leetcode_guard._attempt_store import merge_submissions
from leetcode_guard._history_queries import HistoryPage
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._attempt_helpers import T0
from leetcode_guard.tests._history_helpers import Remote, codes, mirror, row, run
from leetcode_guard.tests._net_fixtures import fake_post

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_long_history_advances_page_by_page(hmac_key: Path):
    """Three pages: the cursor walks 0, 20, 40 and only then is complete."""
    merge_submissions([("99", "two-sum", "Accepted", T0)], now=T0)
    full = HistoryPage((row(99, T0, "Accepted"),), has_next=True)
    remote = Remote(
        {
            0: full,
            20: HistoryPage((row(50, T0 - 50),), has_next=True),
            40: HistoryPage((row(10, T0 - 90),), has_next=False),
        },
        code={},
    )

    for _ in range(3):
        run(remote, hmac_key)

    assert [offset for _, offset in remote.page_calls] == [0, 20, 40]
    assert mirror("two-sum")["complete"] is True


def test_a_burst_of_new_submissions_reopens_a_complete_mirror(hmac_key: Path):
    """Over a page of unseen rows since the last look: the gap is owed again."""
    merge_submissions([("1", "two-sum", "Accepted", T0)], now=T0)
    run(Remote({0: HistoryPage((row(1, T0, "Accepted"),), has_next=False)}), hmac_key)
    merge_submissions([("80", "two-sum", "Wrong Answer", T0 + 500)], now=T0 + 500)
    burst = HistoryPage((row(80, T0 + 500),), has_next=True)

    run(Remote({0: burst}), hmac_key, at=T0 + 560)

    assert mirror("two-sum")["complete"] is False
    assert mirror("two-sum")["next_offset"] == 20


def test_a_slug_that_cannot_name_a_file_is_ignored(hmac_key: Path):
    """attempts.json is editable; ``../x`` must never become a path."""
    merge_submissions([("1", "../escape", "Accepted", T0)], now=T0)

    assert run(Remote({}), hmac_key) == "idle"


def test_an_unreadable_mirror_starts_again(hmac_key: Path):
    """A hand-edited file is rebuilt from LeetCode, never trusted."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    _history_store.HISTORY_DIR.mkdir(parents=True)
    (_history_store.HISTORY_DIR / "two-sum.json").write_text(
        '{"submissions": 3}', encoding="utf-8"
    )
    remote = Remote({0: HistoryPage((row(2, T0, "Accepted"),), has_next=False)})

    assert run(remote, hmac_key) == "two-sum: 1 submission, 1 with code"


def test_code_that_keeps_failing_is_given_up_after_three_reads(hmac_key: Path):
    """A submission whose code never reads must not cost five requests a minute forever."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    remote = Remote(
        {0: HistoryPage((row(2, T0, "Accepted"),), has_next=False)}, code={}
    )

    lines = [run(remote, hmac_key) for _ in range(5)]

    assert remote.code_calls == ["2", "2", "2"]
    assert lines[-1] == "idle"


def test_the_default_fetchers_use_the_harvesters_client(
    monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """Production wiring: one client, both queries through its ``post``."""
    merge_submissions([("2", "two-sum", "Accepted", T0)], now=T0)
    post = fake_post(
        GraphQLResult(
            data={
                "questionSubmissionList": {
                    "hasNext": False,
                    "submissions": [
                        {"id": "2", "statusDisplay": "Accepted", "timestamp": str(T0)}
                    ],
                }
            }
        ),
        GraphQLResult(data={"submissionDetails": {"code": "print(1)"}}),
    )
    monkeypatch.setattr(
        _history_sync, "build_client", lambda: SimpleNamespace(post=post)
    )

    assert _history_sync.history_line(clock=lambda: T0 + 60, key_file=hmac_key) == (
        "two-sum: 1 submission, 1 with code"
    )
    assert codes("two-sum") == {"2": "print(1)"}


def test_a_new_row_on_a_long_complete_history_keeps_it_complete(hmac_key: Path):
    """Page 0 still overlaps the mirror: nothing is owed, no page walk starts."""
    merge_submissions([("1", "two-sum", "Accepted", T0)], now=T0)
    run(Remote({0: HistoryPage((row(1, T0, "Accepted"),), has_next=False)}), hmac_key)
    merge_submissions([("2", "two-sum", "Wrong Answer", T0 + 500)], now=T0 + 500)
    overlap = HistoryPage((row(2, T0 + 500), row(1, T0, "Accepted")), has_next=True)

    run(Remote({0: overlap}), hmac_key, at=T0 + 560)

    assert mirror("two-sum")["complete"] is True
    assert mirror("two-sum")["next_offset"] == 0
