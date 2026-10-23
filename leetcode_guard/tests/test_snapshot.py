"""Tests for the status-app snapshot (TODO-status-app.md schema v1).

Every one of the tkinter window's nine sections must find its data here, and
an unknown value must arrive as ``null`` -- never as a zero the app would
render as a real count.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _status_full, _status_timer
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._profile import Profile
from leetcode_guard._progress import Progress
from leetcode_guard._snapshot import SCHEMA_VERSION, build_snapshot
from leetcode_guard._snapshot_projection import build_projections, projection_targets
from leetcode_guard._status_full import gather_full
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

MONDAY_NOON = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
PROGRESS = Progress(
    solved={"Easy": 10, "Medium": 5, "Hard": 1},
    total={"Easy": 900, "Medium": 1900, "Hard": 850},
    fetched_at=MONDAY_NOON.timestamp(),
)
PROFILE = Profile(
    solved={"Easy": 10, "Medium": 5, "Hard": 1},
    total={"Easy": 900, "Medium": 1900, "Hard": 850},
    calendar={"2026-08-09": 2, "2026-08-10": 1, "2026-08-01": 3},
    acceptance_rate=61.2,
    fetched_at=MONDAY_NOON.timestamp(),
    credit_count=3,
)


@pytest.fixture(autouse=True)
def _timer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _status_full,
        "gather_timer",
        lambda: _status_timer.TimerStatus(
            enabled=True, next_fire="Tue 09:00", detail="enabled"
        ),
    )


def a_full(data_dir: Path, hmac_key: Path):
    path = data_dir / "ledger.json"
    ledger = ledger_with_credits(5, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)
    save_ledger(path, ledger)
    return gather_full(now=MONDAY_NOON, ledger_path=path, key_file=hmac_key)


def a_snapshot(data_dir: Path, hmac_key: Path, **overrides):
    kwargs = {"progress": PROGRESS, "profile": PROFILE, "coach": None}
    kwargs.update(overrides)
    return build_snapshot(a_full(data_dir, hmac_key), now=MONDAY_NOON, **kwargs)


def test_the_envelope(data_dir: Path, hmac_key: Path):
    snap = a_snapshot(data_dir, hmac_key)

    assert snap["schema"] == SCHEMA_VERSION == 1
    assert snap["generated_at"] == MONDAY_NOON.astimezone().isoformat(
        timespec="seconds"
    )
    assert snap["coach"] is None
    json.dumps(snap, allow_nan=False)


def test_verdict_and_credits_sections(data_dir: Path, hmac_key: Path):
    status = a_snapshot(data_dir, hmac_key)["status"]

    assert status["day"] == "2026-08-10"
    assert status["weekday"] == "Monday"
    assert isinstance(status["locked"], bool)
    assert status["reason"]
    assert status["explanation"]
    assert status["charged_today"] is True
    assert status["earned_all_time"] == 5
    assert status["spent_all_time"] >= 1
    assert set(status["debt"]) == {
        "owed",
        "repaid",
        "outstanding",
        "missed_days",
        "summary",
    }
    assert "Tue" in status["pricing_note"]


def test_solves_days_and_budgets_sections(data_dir: Path, hmac_key: Path):
    status = a_snapshot(data_dir, hmac_key)["status"]

    assert status["solves"]["today"] == 5
    assert status["solves"]["last_7_days"] == 5
    assert status["solves"]["total_credited"] == 5
    assert set(status["solves"]["recent"][0]) == {"day", "title_slug", "lang"}
    assert status["days"]["charged"] == ["2026-08-10"]
    assert status["days"]["in_force"] is True
    escape = status["budgets"]["escape"]
    assert set(escape) >= {"used_7", "limit_7", "exhausted", "next_wait_seconds"}
    assert escape["summary"].startswith("Escape hatch:")
    assert status["budgets"]["incidents"]["label"] == "Network incidents"


def test_integrity_environment_and_suggestions_sections(data_dir: Path, hmac_key: Path):
    status = a_snapshot(data_dir, hmac_key)["status"]

    integrity = status["integrity"]
    assert integrity["ok"] is True
    assert integrity["total_entries"] >= 6
    assert integrity["ledger_path"].endswith("ledger.json")
    env = status["environment"]
    assert env["timer"] == {
        "enabled": True,
        "next_fire": "Tue 09:00",
        "detail": "enabled",
    }
    assert env["pool_cache"]["summary"] == "Problem pool: none"
    assert env["pool_cache"]["age_days"] is None
    assert isinstance(env["pool_notes"], list)
    assert {"cookies_configured", "sync_configured", "clock_trusted"} <= set(env)
    assert status["suggestions"] == []


def test_progress_and_profile(data_dir: Path, hmac_key: Path):
    snap = a_snapshot(data_dir, hmac_key)

    assert snap["progress"]["solved"] == {"Easy": 10, "Medium": 5, "Hard": 1}
    assert snap["progress"]["solved_all"] == 16
    assert snap["progress"]["total_all"] == 3650
    profile = snap["profile"]
    assert profile["difficulty"] == {
        "easy": [10, 900],
        "medium": [5, 1900],
        "hard": [1, 850],
    }
    assert (profile["streak_current"], profile["streak_longest"]) == (2, 2)
    assert profile["acceptance_rate"] == 61.2
    assert profile["calendar"]["2026-08-01"] == 3


def test_unknown_sections_are_null_never_zero(data_dir: Path, hmac_key: Path):
    snap = a_snapshot(data_dir, hmac_key, progress=None, profile=None)

    assert snap["progress"] is None
    assert snap["profile"] is None
    first = next(iter(snap["projections"].values()))
    assert first["projected"] is None


def test_a_profile_without_a_calendar_has_unknown_streaks(
    data_dir: Path, hmac_key: Path
):
    profile = Profile(
        solved=PROFILE.solved,
        total=PROFILE.total,
        calendar=None,
        acceptance_rate=None,
        fetched_at=0.0,
    )

    snap = a_snapshot(data_dir, hmac_key, profile=profile)["profile"]

    assert snap["calendar"] is None
    assert snap["streak_current"] is None
    assert snap["streak_longest"] is None
    assert snap["acceptance_rate"] is None


def test_projection_targets_are_90_days_plus_12_month_ends():
    targets = projection_targets(date(2026, 10, 23))

    assert targets[0] == date(2026, 10, 23)
    assert date(2027, 1, 20) in targets
    assert date(2027, 1, 21) not in targets
    month_ends = [d for d in targets if d > date(2027, 1, 20)]
    assert month_ends == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
        date(2027, 5, 31),
        date(2027, 6, 30),
        date(2027, 7, 31),
        date(2027, 8, 31),
        date(2027, 9, 30),
    ]
    assert date(2026, 12, 31) in targets
    assert len(targets) == len(set(targets)) == 99


def test_projections_match_the_window_arithmetic(data_dir: Path, hmac_key: Path):
    """Same numbers as the tkinter "Project" button, at the live price."""
    from leetcode_guard._status_projection import ProjectionInputs, build_report

    full = a_full(data_dir, hmac_key)
    projections = build_projections(full.gate, PROGRESS)
    report = build_report(
        full.gate, PROGRESS, ProjectionInputs(target_text="2026-12-31")
    )

    entry = projections["2026-12-31"]
    assert report.projection is not None
    assert entry["required"] == report.projection.required
    assert entry["rules_demand"] == report.projection.rules_demand
    assert entry["projected"] == report.projection.projected
    assert entry["first_day"] == "2026-08-11"
    assert set(entry) == {
        "target",
        "first_day",
        "gated_days",
        "free_days",
        "sick_days",
        "base_cost",
        "debt",
        "available",
        "required",
        "rules_demand",
        "debt_left_by_rules",
        "projected",
    }
