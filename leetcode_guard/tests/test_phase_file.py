"""Contract C3: the signed theory_phase.json, rewritten only on change."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING

import earned_time
from gatelock.log_integrity import compute_entry_hmac

from leetcode_guard import _phase_file
from leetcode_guard._phase import NONE_STATE, PhaseState
from leetcode_guard._phase_file import read_phase, write_phase
from leetcode_guard.tests._tutor_fixtures import ALGO

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 22, 12, 0).astimezone()
THEORY = PhaseState("a", "theory", ALGO, ("a",))


def test_the_row_has_the_contract_shape_and_verifies(hmac_key: Path):
    """kind/entry_id/day/detail exactly as C3 says, signed over the rest."""
    assert write_phase(THEORY, day=NOW.date(), now=NOW, key_file=hmac_key)
    row = json.loads(_phase_file.PHASE_FILE.read_text(encoding="utf-8"))

    assert {k: row[k] for k in ("kind", "entry_id", "day")} == {
        "kind": "theory_phase",
        "entry_id": "phase",
        "day": "2026-11-22",
    }
    assert row["detail"] == {
        "unit": "a",
        "phase": "theory",
        "teachable": [[ALGO, "a"]],
        "at": NOW.timestamp(),
        "theory_since": NOW.timestamp(),
    }
    # The tutor verifies with earned_time: the other library must agree.
    assert row["hmac"] == earned_time.entry_signature(
        row, hmac_key.read_bytes().strip()
    )


def test_it_is_rewritten_only_when_the_content_changes(hmac_key: Path):
    """Same unit/phase/teachable an hour later: untouched. SOLVE: rewritten."""
    write_phase(THEORY, day=NOW.date(), now=NOW, key_file=hmac_key)
    later = NOW + timedelta(hours=1)

    assert not write_phase(THEORY, day=later.date(), now=later, key_file=hmac_key)
    solve = PhaseState("a", "solve", ALGO, ("a",))
    assert write_phase(solve, day=later.date(), now=later, key_file=hmac_key)
    assert read_phase(hmac_key) == PhaseState("a", "solve")


def test_the_last_signed_phase_reads_back(hmac_key: Path):
    """THEORY carries its teachable modules back; none reads as none."""
    write_phase(THEORY, day=NOW.date(), now=NOW, key_file=hmac_key)
    assert read_phase(hmac_key) == THEORY
    write_phase(NONE_STATE, day=NOW.date(), now=NOW, key_file=hmac_key)
    assert read_phase(hmac_key) == NONE_STATE


def test_an_unsignable_write_keeps_the_old_file(
    missing_key: Path, caplog: pytest.LogCaptureFixture
):
    """No key: nothing written (the tutor would refuse an unsigned file)."""
    with caplog.at_level(logging.WARNING):
        assert not write_phase(THEORY, day=NOW.date(), now=NOW, key_file=missing_key)

    assert not _phase_file.PHASE_FILE.exists()
    assert "not rewritten" in caplog.text


def test_a_failed_write_is_logged(
    monkeypatch: pytest.MonkeyPatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """A full disk costs the rewrite, never the caller."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr(_phase_file, "write_json", refuse)

    with caplog.at_level(logging.WARNING):
        assert not write_phase(THEORY, day=NOW.date(), now=NOW, key_file=hmac_key)

    assert "cannot write" in caplog.text


def test_a_forged_or_misshapen_file_is_no_phase(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Edited, not an object, or a bad shape under a good signature: ``None``."""
    write_phase(THEORY, day=NOW.date(), now=NOW, key_file=hmac_key)
    path = _phase_file.PHASE_FILE
    row = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**row, "day": "2030-01-01"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_phase(hmac_key) is None
        path.write_text("[]", encoding="utf-8")
        assert read_phase(hmac_key) is None
        for detail in (
            {"unit": "a", "phase": "learn", "teachable": []},
            {"unit": 1, "phase": "none", "teachable": []},
            {"unit": "a", "phase": "theory", "teachable": [["only-one"]]},
            {"unit": "a", "phase": "theory", "teachable": "x"},
        ):
            body = {
                "kind": "theory_phase",
                "entry_id": "phase",
                "day": "d",
                "detail": detail,
            }
            signed = {**body, "hmac": compute_entry_hmac(body, key_file=hmac_key)}
            path.write_text(json.dumps(signed), encoding="utf-8")
            expected = PhaseState("a", "theory") if detail["teachable"] == "x" else None
            assert read_phase(hmac_key) == expected

    assert "fails its signature" in caplog.text
    assert "bad shape" in caplog.text
