"""``--flagged``: the text lines, the summary, ``--json`` and its misuse."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import (
    _attempt_paths,
    _attempt_report,
    _cli,
    _coach_reviews,
    _constants,
    _flagged_cli,
)
from leetcode_guard._attempt_model import Submission, to_document
from leetcode_guard.tests._flagged_fixtures import (
    NOW,
    T0,
    beat_run,
    record_of,
    records_of,
    write_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def seeded(hmac_key: Path) -> None:
    """Three solves: a flagged one with failures, a fast one, one with no beats."""
    write_credits(
        _constants.LEDGER_FILE,
        [("1", "long-one", T0), ("2", "quick", T0 - 7200), ("3", "ghost", T0 - 9000)],
        hmac_key,
    )
    slow = record_of(
        "long-one",
        beat_run(T0, 26),
        submissions={
            "a": Submission("Wrong Answer", T0 - 600),
            "b": Submission("Wrong Answer", T0 - 300),
            "c": Submission("Runtime Error", T0 - 100),
        },
        theory="done",
    )
    quick = record_of("quick", beat_run(T0 - 7200, 4), at=T0 - 7200, theory="done")
    _attempt_paths.ATTEMPTS_FILE.write_text(
        json.dumps(to_document(records_of(slow, quick))), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command reads the real clock; pin it to an hour after the accept."""
    monkeypatch.setattr(
        _flagged_cli,
        "load_report",
        lambda **kwargs: _attempt_report.load_report(now=NOW, **kwargs),
    )


def test_with_nothing_flagged_only_the_summary_line_prints(
    capsys: pytest.CaptureFixture[str],
):
    """No data at all: one line, share ``n/a``, exit 0."""
    assert _cli.main(["--flagged"]) == 0

    assert capsys.readouterr().out == "measured 0, unknown 0, under 10 min n/a\n"


@pytest.mark.usefixtures("seeded")
def test_a_flagged_solve_prints_its_evidence_then_the_summary(
    capsys: pytest.CaptureFixture[str],
):
    """Slug, active, span, failed by kind, first submission, minutes per tab."""
    assert _cli.main(["--flagged"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "long-one  active 25m  span 25m  failed 1 Runtime Error, 2 Wrong Answer"
        "  first submit 15m"
        "  tabs description 25m editorial 0m solutions 0m submissions 0m",
        "measured 2, unknown 1, under 10 min 50%",
    ]


@pytest.mark.usefixtures("seeded")
def test_a_solve_without_failures_or_span_prints_none_and_na(
    capsys: pytest.CaptureFixture[str],
):
    """``failed none`` and ``span n/a`` rather than an empty or missing field."""
    day_before = T0 - 86_400
    long_ago = record_of("long-one", beat_run(day_before, 26), at=day_before)
    stray = record_of("long-one", [], theory="done")
    _attempt_paths.ATTEMPTS_FILE.write_text(
        json.dumps(to_document(records_of(long_ago, stray))), encoding="utf-8"
    )

    assert _cli.main(["--flagged"]) == 0

    out = capsys.readouterr().out
    assert "long-one  active 25m  span n/a  failed none  first submit 25m" in out


@pytest.mark.usefixtures("seeded")
def test_json_is_one_document_with_stable_keys(capsys: pytest.CaptureFixture[str]):
    """The same report the MCP tool returns, keys sorted."""
    assert _cli.main(["--flagged", "--json"]) == 0

    out = capsys.readouterr().out
    report = json.loads(out)
    assert [row["slug"] for row in report["flagged"]] == ["long-one"]
    assert out == json.dumps(report, sort_keys=True, indent=2) + "\n"
    assert report == _attempt_report.load_report(now=NOW)


def test_json_without_flagged_is_an_argument_error(capsys: pytest.CaptureFixture[str]):
    """argparse's exit 2, and nothing on stdout."""
    with pytest.raises(SystemExit) as stop:
        _cli.main(["--json"])

    assert stop.value.code == 2
    assert "--json needs --flagged" in capsys.readouterr().err


@pytest.mark.usefixtures("seeded")
def test_the_command_writes_nothing():
    """Read-only over both files: bytes and the directory listing are unchanged."""
    data = _constants.DATA_DIR
    before = {path.name: path.read_bytes() for path in data.iterdir()}

    _cli.main(["--flagged"])
    _cli.main(["--flagged", "--json"])

    assert {path.name: path.read_bytes() for path in data.iterdir()} == before


def _coach_log_of(slug: str, *events: object) -> None:
    folder = _coach_reviews.COACH_SESSIONS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"2026-11-21-{slug}.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )


@pytest.mark.usefixtures("seeded")
def test_a_finished_review_clears_the_flag(capsys: pytest.CaptureFixture[str]):
    """A ``review`` with a named cause in the coach log: no row, same summary."""
    _coach_log_of("long-one", {"event": "review", "cause": "idea-to-code"})

    assert _cli.main(["--flagged"]) == 0

    assert capsys.readouterr().out == "measured 2, unknown 1, under 10 min 50%\n"


@pytest.mark.usefixtures("seeded")
def test_a_review_without_a_cause_leaves_the_flag(capsys: pytest.CaptureFixture[str]):
    """An unfinished review is not a review: the row still prints."""
    _coach_log_of("long-one", {"event": "review"}, {"event": "postmortem"})

    assert _cli.main(["--flagged", "--json"]) == 0

    flagged = json.loads(capsys.readouterr().out)["flagged"]
    assert [row["slug"] for row in flagged] == ["long-one"]


@pytest.mark.usefixtures("seeded")
def test_an_unreadable_coach_log_keeps_the_flag(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
):
    """Could not check: a warning, the row stays, and the command still exits 0."""
    folder = _coach_reviews.COACH_SESSIONS_DIR
    folder.parent.mkdir(parents=True, exist_ok=True)
    folder.write_text("a file where the folder should be", encoding="utf-8")

    assert _cli.main(["--flagged"]) == 0

    assert capsys.readouterr().out.startswith("long-one  active 25m")
    assert "could not check" in caplog.text
