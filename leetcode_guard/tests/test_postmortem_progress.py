"""The running post-mortem's progress row: tolerant, clock-free, display-only."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_guard import _postmortem_progress
from leetcode_guard._postmortem_progress import read_progress, snapshot_progress
from leetcode_guard.tests._postmortem_fixtures import postmortems_dir

if TYPE_CHECKING:
    from pathlib import Path

# The shape tutor/postmortem/progress.py wrote for prefix-sums rev 1 while it
# ran (2026-11-28), stage moved on and the summary filled in by hand.
RUNNING: dict[str, Any] = {
    "version": 1,
    "state": "running",
    "unit": "prefix-sums",
    "subject": "leetcode-easy-algorithms-in-typescript",
    "rev": 1,
    "stage": "applying",
    "started_at": 1795892160.0,
    "stage_at": 1795892700.0,
    "finished_at": None,
    "estimate_s": 660.0,
    "durations": [],
    "summary": None,
    "error": None,
}


def _write(doc: object) -> Path:
    path = postmortems_dir() / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_no_file_is_none():
    """No post-mortem has reported progress yet."""
    assert read_progress() is None


def test_a_running_post_mortem_ships_its_stage_and_eta_inputs():
    """Every key ships; the subject and kept durations stay on the PC."""
    _write(RUNNING)

    assert read_progress() == {
        "state": "running",
        "unit": "prefix-sums",
        "rev": 1,
        "stage": "applying",
        "started_at": 1795892160.0,
        "stage_at": 1795892700.0,
        "finished_at": None,
        "estimate_s": 660.0,
        "summary": None,
        "error": None,
    }


def test_a_finished_one_keeps_its_summary_and_error():
    """Unknown summary keys and non-int counts drop; the error is capped."""
    _write(
        {
            **RUNNING,
            "state": "failed",
            "stage": None,
            "finished_at": 1795892800,
            "summary": {"added": 9, "edited": True, "bogus": 3, "suspended": 2},
            "error": "x" * 500,
        }
    )

    row = read_progress()

    assert row is not None
    assert row["state"] == "failed"
    assert row["finished_at"] == 1795892800.0
    assert row["summary"] == {"added": 9, "suspended": 2}
    assert row["error"] == "x" * _postmortem_progress.ERROR_CAP


def test_bad_fields_read_as_unknown():
    """A wrong type, a negative time or an unknown stage is ``None``, not 0."""
    _write(
        {
            "state": "running",
            "unit": 5,
            "rev": True,
            "stage": "dreaming",
            "started_at": -1,
            "stage_at": "soon",
            "estimate_s": False,
            "summary": [1],
        }
    )

    row = read_progress()

    assert row is not None
    assert {k for k, v in row.items() if v is None} == {
        "unit",
        "rev",
        "stage",
        "started_at",
        "stage_at",
        "finished_at",
        "estimate_s",
        "summary",
        "error",
    }


@pytest.mark.parametrize("doc", [[1], {"state": "paused"}, {}])
def test_a_file_that_is_not_progress_is_skipped(
    doc: object, caplog: pytest.LogCaptureFixture
):
    """Not a dict, or an unknown state: warned, and no row."""
    _write(doc)

    with caplog.at_level(logging.WARNING):
        assert read_progress() is None

    assert "not a post-mortem progress file" in caplog.text


def test_unreadable_json_is_none():
    """A cut write is the reader's warning, never a raise."""
    path = postmortems_dir() / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{cut", encoding="utf-8")

    assert read_progress() is None


def test_an_explicit_root_is_read(tmp_path: Path):
    """``root`` points at another tutor data dir."""
    (tmp_path / "postmortems").mkdir()
    (tmp_path / "postmortems" / "progress.json").write_text(json.dumps(RUNNING))

    row = read_progress(tmp_path)

    assert row is not None
    assert row["unit"] == "prefix-sums"


def test_snapshot_progress_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A raise inside the reader is a warning and an unknown section."""

    def boom(_root: object = None) -> None:
        raise RuntimeError

    monkeypatch.setattr(_postmortem_progress, "read_progress", boom)

    with caplog.at_level(logging.WARNING):
        assert snapshot_progress() is None

    assert "section unknown" in caplog.text
