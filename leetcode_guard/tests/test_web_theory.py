"""``GET /api/theory``: the guard's LeetCode theory accounting, read-only.

The tutor's lesson bar fetches it (server to server, loopback) and only shows
it. The scenario is ``_theory_scenario``'s: unit ``a`` (module ``a``, Easy
``a1``) then unit ``b``. On the Tuesday of ``NOW`` a day costs 2.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from leetcode_guard import _web_theory
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._theory_credit import poll_theory
from leetcode_guard._web_theory import build_theory_payload
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests.test_status_unit import minted
from leetcode_guard.tests.test_unit_view import solved

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
KEYS = (
    "checked",
    "day",
    "unit",
    "phase",
    "minutes_today",
    "minutes_into_credit",
    "minutes_per_credit",
    "credits_today",
    "needed",
)


def theory(key: Path) -> dict[str, object]:
    """The ``theory`` block at :data:`NOW`."""
    block = build_theory_payload(now=NOW, key_file=key)["theory"]
    assert isinstance(block, dict)
    return block


def test_in_theory_it_counts_the_minutes_towards_the_next_credit(
    tmp_path, monkeypatch, hmac_key: Path
):
    """THEORY(a), 7 minutes, nothing minted: 7 of 12, the day still owes 2."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 7))

    payload = build_theory_payload(now=NOW, key_file=hmac_key)

    assert payload == {
        "theory": {
            "checked": True,
            "day": "2026-11-24",
            "unit": "a",
            "phase": "theory",
            "minutes_today": 7,
            "minutes_into_credit": 7,
            "minutes_per_credit": 12,
            "credits_today": 0,
            "needed": 2,
        }
    }
    assert tuple(payload["theory"]) == KEYS


def test_a_credit_due_but_not_minted_reads_a_full_twelve_then_zero(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """12 minutes: pending mint shows 12; once minted the next credit starts at 0."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 12))

    assert theory(hmac_key)["minutes_into_credit"] == 12

    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=NOW, key_file=hmac_key)
    after = theory(hmac_key)

    assert (after["minutes_today"], after["minutes_into_credit"]) == (12, 0)
    assert (after["credits_today"], after["needed"]) == (1, 1)


def test_minutes_past_the_minted_credits_are_the_remainder(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """30 minutes with two minted (24 paid for): 6 into the third."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    minted(data_dir, hmac_key, (0, "a"), (0, "a"))

    block = theory(hmac_key)

    assert (block["minutes_today"], block["minutes_into_credit"]) == (30, 6)
    assert block["credits_today"] == 2
    assert block["needed"] == 0


def test_solve_phase_still_counts_minutes_taught_before_the_flip(
    tmp_path, monkeypatch, hmac_key: Path
):
    """SOLVE(a): the phase machine's own word, minutes before the flip pay."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", at=NOW.timestamp() - 30)
    taught(hmac_key, NOW, ("a", 5))

    block = theory(hmac_key)

    assert (block["unit"], block["phase"]) == ("a", "solve")
    assert (block["minutes_today"], block["minutes_into_credit"]) == (5, 5)


def test_every_unit_finished_is_none_with_zero_minutes(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No unit: the guard's own ``""`` and ``none``; nothing counts, all checked."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1", "b1-easy")

    block = theory(hmac_key)

    assert (block["unit"], block["phase"]) == ("", "none")
    assert (block["minutes_today"], block["minutes_into_credit"]) == (0, 0)
    assert block["checked"] is True


def test_unreadable_tutor_minutes_are_null_never_zero(
    tmp_path, monkeypatch, hmac_key: Path
):
    """No signed tutor ledger: the phase is known, the minutes are not."""
    world(tmp_path, monkeypatch)
    states(hmac_key)

    block = theory(hmac_key)

    assert (block["unit"], block["phase"]) == ("a", "theory")
    assert block["minutes_today"] is None
    assert block["minutes_into_credit"] is None
    assert block["checked"] is False
    assert block["credits_today"] == 0
    assert block["needed"] == 2


def test_an_undecidable_phase_is_null_everywhere_it_leads(
    tmp_path, monkeypatch, hmac_key: Path
):
    """No signed C2: unit, phase and both minute fields are null."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW, ("a", 7))

    block = theory(hmac_key)

    assert [block[k] for k in ("unit", "phase")] == [None, None]
    assert block["minutes_today"] is None
    assert block["minutes_into_credit"] is None
    assert block["checked"] is False
    assert block["minutes_per_credit"] == 12
    assert block["day"] == "2026-11-24"


def test_only_trusted_credits_count(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """A forged theory row (bad signature) is not a minted credit."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 7))
    minted(data_dir, hmac_key, (0, "a"))
    path = data_dir / "ledger.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"][0]["amount"] = 5
    path.write_text(json.dumps(document), encoding="utf-8")

    assert theory(hmac_key)["credits_today"] == 0


def test_a_bug_inside_answers_nulls_and_logs_a_warning(
    tmp_path, monkeypatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Fail-open to null: nothing raises into the handler, the journal hears it."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    caplog.set_level(logging.WARNING)

    with patch.object(_web_theory, "decide_today", side_effect=RuntimeError("boom")):
        block = theory(hmac_key)

    assert block == {
        "checked": False,
        "day": "2026-11-24",
        "unit": None,
        "phase": None,
        "minutes_today": None,
        "minutes_into_credit": None,
        "minutes_per_credit": 12,
        "credits_today": None,
        "needed": None,
    }
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_it_writes_nothing(tmp_path, monkeypatch, data_dir: Path, hmac_key: Path):
    """Not the ledger, not C3, not the pool: a credit due is shown, never minted."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    theory(hmac_key)

    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    assert not (data_dir / "ledger.json").exists()
    assert not (data_dir / "theory_phase.json").exists()
