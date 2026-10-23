"""The Coach tab before any session: a known state, not an unknown one.

``coach: null`` made the app print "unknown" everywhere with no way forward
(2026-10-23). With no session logs the coach section is a real one -- no
problems, no re-tests, every cluster at zero with its problem list and the
``how_to`` block -- and ``None`` is reserved for a derivation that failed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from leetcode_coach import how_to, progress
from leetcode_guard import _coach_log
from leetcode_guard._coach_log import read_coach

if TYPE_CHECKING:
    import pytest

APP_FIXTURES = Path(__file__).parents[2] / "app" / "test" / "fixtures"
NAMES = [
    "bit-cancellation",
    "two-pointers",
    "sliding-window",
    "prefix-sum-hash",
    "monotonic-stack",
    "intervals",
]


def known_empty(tmp_path: Path) -> dict[str, Any]:
    coach = read_coach(tmp_path / "never-created")
    assert coach is not None
    return coach


def test_no_sessions_dir_is_a_known_empty_coach(tmp_path: Path):
    coach = known_empty(tmp_path)

    assert coach["problems"] == []
    assert coach["retests_due"] == []
    assert list(coach["clusters"]) == NAMES


def test_an_empty_sessions_dir_is_the_same_known_empty_coach(tmp_path: Path):
    (tmp_path / "sessions").mkdir()

    assert read_coach(tmp_path / "sessions") == known_empty(tmp_path)


def test_every_cluster_starts_at_zero_with_its_problems_and_next(tmp_path: Path):
    clusters = known_empty(tmp_path)["clusters"]

    first = clusters["bit-cancellation"]
    assert {k: first[k] for k in ("total", "started", "solved", "next", "order")} == {
        "total": 4,
        "started": 0,
        "solved": 0,
        "next": "missing-number",
        "order": 0,
    }
    assert first["problems"][0] == {
        "slug": "missing-number",
        "number": 268,
        "title": "Missing Number",
        "url": "https://leetcode.com/problems/missing-number/",
    }
    assert [c["order"] for c in clusters.values()] == list(range(len(NAMES)))
    for name, cluster in clusters.items():
        listed = progress.load_clusters()[name]
        assert [p["slug"] for p in cluster["problems"]] == [p["slug"] for p in listed]
        assert cluster["total"] == len(listed)
        assert cluster["next"] == listed[0]["slug"]
        assert all(p["title"] for p in cluster["problems"])
        assert all(
            p["url"].endswith(f"/problems/{p['slug']}/") for p in cluster["problems"]
        )


def test_how_to_carries_the_commands_the_method_and_the_first_command(
    tmp_path: Path,
):
    block = known_empty(tmp_path)["how_to"]

    assert block == how_to.block("bit-cancellation")
    assert block["first_command"] == "leetcode --cluster bit-cancellation"
    assert [c["command"] for c in block["commands"]] == [
        "leetcode --cluster <name>",
        "leetcode <url>",
        "leetcode due",
        "leetcode report",
    ]
    assert [s["name"] for s in block["steps"]] == [
        "Constraint",
        "Requirements",
        "Toolbox",
        "Post-mortem",
    ]


def test_the_empty_fixture_is_what_the_exporter_writes(tmp_path: Path):
    # The app's empty-state fixture is copied from this output, never typed:
    # the fixture once spelled a key the exporter does not emit (done/solved).
    fixture = json.loads((APP_FIXTURES / "snapshot_coach_empty.json").read_text())

    assert fixture["coach"] == known_empty(tmp_path)


def test_sessions_keep_the_cluster_problem_lists_and_add_the_retest_command(
    tmp_path: Path,
):
    for name in ("2026-01-02-missing-number.jsonl",):
        (tmp_path / name).write_text(
            '{"event": "code"}\n{"event": "postmortem"}\n', encoding="utf-8"
        )

    coach = read_coach(tmp_path)

    assert coach is not None
    assert coach["clusters"]["bit-cancellation"]["solved"] == 1
    assert coach["clusters"]["bit-cancellation"]["next"] == "single-number-iii"
    assert len(coach["clusters"]["bit-cancellation"]["problems"]) == 4
    assert [r["command"] for r in coach["retests_due"]] == [
        "leetcode --retest missing-number"
    ]
    assert coach["how_to"] == how_to.block("bit-cancellation")


def test_a_failing_session_reader_is_unknown_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    (tmp_path / "2026-01-02-x.jsonl").write_text("{}\n", encoding="utf-8")

    def boom(_path: Path) -> object:
        message = "disk on fire"
        raise RuntimeError(message)

    monkeypatch.setattr(_coach_log, "read_session", boom)

    assert read_coach(tmp_path) is None
    assert "disk on fire" in caplog.text


def test_a_failing_cluster_file_drops_the_derived_blocks_not_the_coach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def boom(_path: Path | None = None) -> object:
        message = "clusters.json is gone"
        raise OSError(message)

    monkeypatch.setattr(progress, "load_clusters", boom)

    coach = read_coach(tmp_path)

    assert coach is not None
    assert coach["problems"] == []
    assert coach["clusters"] is None
    assert coach["how_to"] is None
    assert "clusters.json is gone" in caplog.text
