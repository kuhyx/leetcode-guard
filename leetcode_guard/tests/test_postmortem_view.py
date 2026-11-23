"""The post-mortem view: the tutor's reports, read for display only."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _postmortem_view
from leetcode_guard._postmortem_view import (
    FINDING_CAP,
    read_postmortems,
    snapshot_postmortems,
)
from leetcode_guard.tests._postmortem_fixtures import (
    APP_FIXTURE,
    postmortems_dir,
    reports,
    write_all,
    write_report,
)

if TYPE_CHECKING:
    import pytest


def _unit(name: str) -> dict:
    """The model row of one unit, read from the fixture reports."""
    write_all()
    rows = read_postmortems()
    assert rows is not None
    return next(row for row in rows if row["unit"] == name)


def test_no_reports_dir_is_a_known_empty_list():
    """No post-mortem yet is ``[]``, never unknown."""
    assert read_postmortems() == []


def test_units_come_oldest_first_with_their_latest_rates():
    """The chart's order: by the latest revision's time."""
    write_all()

    rows = read_postmortems()

    assert rows is not None
    assert [row["unit"] for row in rows] == ["two-pointers", "prefix-sums"]
    assert rows[1]["post"] == [0, 3]
    assert rows[1]["pre"] == [1, 7]
    assert rows[1]["rev"] == 2


def test_the_latest_revision_wins_whatever_its_position():
    """Revision order in the file does not decide; the highest ``rev`` does."""
    report = reports()["prefix-sums"]
    report["revisions"].reverse()
    write_report(report)

    rows = read_postmortems()

    assert rows is not None
    assert rows[0]["rev"] == 2
    assert len(rows[0]["problems"]) == 10


def test_problem_rows_keep_the_grid_fields_and_unknown_minutes():
    """A missing time stays ``None`` (shown as ``?``), never 0."""
    problems = _unit("prefix-sums")["problems"]

    first = problems[0]
    assert set(first) == {"slug", "tries", "minutes", "one_shot", "phase", "finding"}
    assert first["slug"] == "left-and-right-sum-differences"
    assert first["minutes"] is None
    assert first["tries"] == 11
    assert first["phase"] == "pre"
    assert problems[-1]["minutes"] == 18
    assert all(len(row["finding"]) <= FINDING_CAP for row in problems)


def test_card_chips_new_edited_suspended_kept_in_that_order():
    """Unchanged cards are not chips; suspended cards carry the applied reason."""
    cards = _unit("prefix-sums")["cards"]

    assert [card["kind"] for card in cards] == [
        *["new"] * 5,
        *["edited"] * 3,
        "suspended",
        "kept",
    ]
    suspended = cards[8]
    assert suspended["finding"].startswith("Recited without a miss")
    assert cards[-1]["used_by"] == ["running-sum-of-1d-array", "ant-on-the-boundary"]
    assert cards[5]["front"].startswith("A single pass builds running totals")
    assert cards[0]["finding"].startswith("No card says the other side")


def test_a_long_finding_is_cut_at_the_cap():
    """The cap keeps the snapshot small; the cut is marked."""
    report = reports()["two-pointers"]
    report["revisions"][0]["problems"][0]["finding"] = "x" * 1000
    write_report(report)

    rows = read_postmortems()

    assert rows is not None
    finding = rows[0]["problems"][0]["finding"]
    assert len(finding) == FINDING_CAP
    assert finding.endswith("…")


def test_dry_failed_tasks_and_side_files_are_not_reports():
    """Only ``<subject>/<unit>.json`` counts."""
    report = reports()["two-pointers"]
    for folder in ("dry", "failed", "tasks"):
        path = postmortems_dir() / folder / "two-pointers.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(report), encoding="utf-8")
    write_report(report, name="lessons")
    write_report(report, name="revisions")

    assert read_postmortems() == []


def test_a_broken_report_is_skipped_and_logged(caplog: pytest.LogCaptureFixture):
    """One bad file costs only itself."""
    write_all()
    bad = postmortems_dir() / "s" / "torn.json"
    bad.parent.mkdir()
    bad.write_text("{", encoding="utf-8")
    wrong = dict(reports()["two-pointers"], kind="other", unit="wrong")
    write_report(wrong)
    empty = dict(reports()["two-pointers"], revisions=[], unit="empty")
    write_report(empty)
    rows_only = dict(reports()["two-pointers"], revisions=["x"], unit="rows")
    write_report(rows_only)
    write_report(dict(reports()["two-pointers"], unit=3), name="numbered")

    rows = read_postmortems()

    assert rows is not None
    assert [row["unit"] for row in rows] == ["two-pointers", "prefix-sums"]
    assert "torn.json" in caplog.text
    assert caplog.text.count("not a post-mortem report") == 4


def test_malformed_fields_read_as_unknown():
    """Wrong types become ``None``; non-object rows are dropped."""
    report = reports()["two-pointers"]
    latest = report["revisions"][0]
    latest["one_shot"] = {"post": [1, "3"], "pre": "x"}
    latest["problems"] = [7, {"slug": 3, "tries": "2", "one_shot": "yes"}]
    latest["cards"] = ["x", {"change": "kept", "used_by": [1, "a"], "finding": 2}]
    latest["new_cards"] = "nope"
    latest["applied"] = "nope"
    latest["at"] = "later"
    write_report(report)

    rows = read_postmortems()

    assert rows is not None
    assert len(rows) == 1
    row = rows[0]
    assert (row["post"], row["pre"], row["at"]) == (None, None, None)
    assert row["problems"] == [
        {
            "slug": "",
            "tries": None,
            "minutes": None,
            "one_shot": False,
            "phase": None,
            "finding": "",
        }
    ]
    assert row["cards"] == [
        {"kind": "kept", "front": "", "finding": "", "used_by": ["a"]}
    ]


def test_the_snapshot_drops_detail_oldest_first_to_fit():
    """Rates always ship; detail goes when the section would be too big."""
    write_all()

    rows = snapshot_postmortems(max_bytes=2000)

    assert rows is not None
    assert [row["post"] for row in rows] == [[2, 3], [0, 3]]
    assert rows[0]["problems"] is None
    assert rows[0]["cards"] is None
    assert rows[1]["problems"] is None


def test_the_snapshot_keeps_only_the_newest_units(
    monkeypatch: pytest.MonkeyPatch,
):
    """A unit count cap, newest kept."""
    write_all()
    monkeypatch.setattr(_postmortem_view, "MAX_UNITS", 1)

    rows = snapshot_postmortems()

    assert rows is not None
    assert [row["unit"] for row in rows] == ["prefix-sums"]


def test_the_snapshot_section_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A bug inside is ``None`` (unknown) and a warning, never a failed push."""

    def explode() -> list[dict]:
        raise RuntimeError

    monkeypatch.setattr(_postmortem_view, "read_postmortems", explode)

    assert snapshot_postmortems() is None
    assert "post-mortem view failed" in caplog.text


def test_the_app_fixture_is_what_the_exporter_writes():
    """``snapshot_postmortem.json``'s section cannot drift from this reader."""
    write_all()
    app = json.loads(APP_FIXTURE.read_text(encoding="utf-8"))

    assert snapshot_postmortems() == app["postmortems"]
