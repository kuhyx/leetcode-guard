"""The flagged-solve report: windows, ordering, the share, and read-only loading."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _attempt_paths, _constants
from leetcode_guard._attempt_model import Submission, to_document
from leetcode_guard._attempt_report import build_report, load_report
from leetcode_guard._attempts import Credit
from leetcode_guard.tests._flagged_fixtures import (
    DAY_SECONDS,
    MINUTE,
    NOW,
    T0,
    beat_run,
    record_of,
    records_of,
    solve_dict,
    write_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

ROW_KEYS = {
    "slug",
    "accepted_at",
    "day",
    "active_seconds",
    "span_seconds",
    "tab_seconds",
    "failed",
    "first_submission_active_seconds",
    "theory",
    "flagged",
}


def long_solve(slug: str, at: int, minutes: int, theory: str = "done"):
    """A record of ``minutes`` minutes of beats ending at ``at``."""
    return record_of(slug, beat_run(at, minutes + 1), at=at, theory=theory)


def test_an_empty_report_has_no_share_rather_than_zero():
    """No measured solve: ``null`` means "no data", never a share of 0."""
    report = build_report([], {}, now=NOW)

    assert report["threshold_seconds"] == 1200
    assert report["window_days"] == 28
    assert report["flagged"] == []
    assert report["measured"] == []
    assert report["unknown"] == []
    assert report["under_10_min_share"] is None
    assert report["generated_at"] == NOW.astimezone().isoformat()


def test_a_report_row_has_every_field_and_the_report_is_json():
    """Plain data only, so the CLI and the MCP tool can return it as is."""
    records = records_of(
        record_of(
            "a",
            beat_run(T0, 3),
            submissions={"1": Submission("Wrong Answer", T0 - 60)},
            theory="done",
        )
    )

    report = build_report([Credit("a", T0)], records, now=NOW)
    row = solve_dict(report, "a")

    assert set(row) == ROW_KEYS
    assert (
        row["accepted_at"]
        == datetime.fromtimestamp(T0, tz=UTC).astimezone().isoformat()
    )
    assert row["failed"] == {"Wrong Answer": 1}
    assert json.loads(json.dumps(report)) == report


def test_lists_are_newest_first():
    """``measured``, ``flagged`` and ``unknown`` all sort by accept time, descending."""
    earned = [Credit("a", T0 - 7200), Credit("b", T0), Credit("c", T0 - 3600)]
    records = records_of(*(long_solve(c.slug, c.accepted_at, 25) for c in earned))

    report = build_report(earned, records, now=NOW)

    assert [row["slug"] for row in report["measured"]] == ["b", "c", "a"]
    assert [row["slug"] for row in report["flagged"]] == ["b", "c", "a"]
    silent = build_report(earned, {}, now=NOW)
    assert [row["slug"] for row in silent["unknown"]] == ["b", "c", "a"]
    assert silent["unknown"][0] == {
        "slug": "b",
        "accepted_at": datetime.fromtimestamp(T0, tz=UTC).astimezone().isoformat(),
    }


def test_a_repeat_credit_does_not_make_a_second_solve():
    """Two credits of one slug: one solve, measured at the earlier time."""
    earned = [Credit("a", T0), Credit("a", T0 - 3600)]
    records = records_of(long_solve("a", T0 - 3600, 5))

    report = build_report(earned, records, now=NOW)

    assert [row["active_seconds"] for row in report["measured"]] == [5 * MINUTE]


def test_measured_and_unknown_cover_28_days_but_flagged_covers_the_retention():
    """An old flagged solve still shows; an old fast or unknown one does not."""
    old = T0 - 29 * DAY_SECONDS
    earned = [
        Credit("old-long", old),
        Credit("old-fast", old),
        Credit("old-none", old),
    ]
    records = records_of(
        long_solve("old-long", old, 25), long_solve("old-fast", old, 2)
    )

    report = build_report(earned, records, now=NOW)

    assert [row["slug"] for row in report["flagged"]] == ["old-long"]
    assert report["measured"] == []
    assert report["unknown"] == []
    assert report["under_10_min_share"] is None


def test_the_share_counts_only_measured_solves_of_the_window():
    """Under 600 s over measured; unknown solves are not in either count."""
    earned = [Credit("fast", T0), Credit("slow", T0 - 60), Credit("ghost", T0 - 120)]
    records = records_of(
        long_solve("fast", T0, 9, theory="none"),
        long_solve("slow", T0 - 60, 10, theory="none"),
    )

    report = build_report(earned, records, now=NOW)

    assert report["under_10_min_share"] == pytest.approx(0.5)
    assert len(report["unknown"]) == 1


def test_a_cleared_slug_is_not_flagged():
    """The review loop's output, once a later stage fills it."""
    earned = [Credit("a", T0)]
    records = records_of(long_solve("a", T0, 25))

    report = build_report(earned, records, now=NOW, cleared=frozenset({"a"}))

    assert report["flagged"] == []
    assert solve_dict(report, "a")["flagged"] is False


def test_load_report_reads_both_files_and_writes_nothing(
    data_dir: Path, hmac_key: Path
):
    """The ledger credit plus ``attempts.json`` give a flagged row; no file changes."""
    write_credits(_constants.LEDGER_FILE, [("77", "a", T0)], hmac_key)
    store = _attempt_paths.ATTEMPTS_FILE
    store.write_text(
        json.dumps(to_document(records_of(long_solve("a", T0, 25)))),
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in data_dir.iterdir()}

    report = load_report(now=NOW)

    assert [row["slug"] for row in report["flagged"]] == ["a"]
    assert {path: path.read_bytes() for path in data_dir.iterdir()} == before


@pytest.mark.usefixtures("data_dir")
def test_load_report_with_no_files_is_an_empty_report():
    """A fresh install has neither file; that is data-less, not an error."""
    report = load_report(now=NOW)

    assert report["measured"] == []
    assert report["under_10_min_share"] is None


def test_load_report_defaults_to_the_clock(data_dir: Path):
    """No ``now``: the report is stamped with the current time."""
    report = load_report()

    assert report["generated_at"][:4].isdigit()
    assert not list(data_dir.iterdir())
