"""Golden C1/C2 rows written by the TUTOR's own code, read by the guard.

``tutor_measured_2026-11-22.json`` was produced on 2026-11-22 by running the
tutor's writers -- ``tutor.credit.build_row`` (C1, with and without the
``subject``/``module`` keys) and ``tutor.curriculum.module_state._row`` (C2) --
from ``~/data/claude-scratch/lc-stage4/wt-tutor`` at 77485f8, which contains
706dcb4 (only the live teaching session's rows carry C1 keys) and 65bf1be
(signed ``module_state.json`` flips, ``entry_id`` ``state:<s>:<m>:<n>`` with
``n`` counting that module's rows), with a fixed test key that is in the file.
The generator is ``~/data/claude-scratch/lc-stage4/gen_tutor_fixture.py``.

Unlike ``_tutor_fixtures`` (rows built here, to the shape measured above), these
rows were never touched by guard code, so a drift in the tutor's row shape or
signing shows up here first. Regenerate on any tutor contract change.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import earned_time
from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard import _tutor_signed
from leetcode_guard._tutor_minutes import teaching_minutes
from leetcode_guard._tutor_signed import module_states, signed_rows
from leetcode_guard.tests._tutor_fixtures import ALGO

GOLDEN = Path(__file__).with_name("tutor_measured_2026-11-22.json")
DOC = json.loads(GOLDEN.read_text(encoding="utf-8"))
MODULE = "prefix-sums"


def _key(tmp_path: Path) -> Path:
    """The fixture's test key, as a key file."""
    path = tmp_path / "tutor.key"
    path.write_bytes(DOC["key"].encode())
    return path


def _install(name: str, document: object) -> None:
    """Copy one of the golden documents into the scratch tutor dir, verbatim."""
    _tutor_signed.TUTOR_DIR.mkdir(parents=True, exist_ok=True)
    (_tutor_signed.TUTOR_DIR / name).write_text(json.dumps(document), encoding="utf-8")


def _rows() -> list[dict[str, object]]:
    """Every golden row, C1 and C2."""
    return [*DOC["ledger"]["entries"], *DOC["module_state"]["entries"]]


def test_tutor_signed_rows_verify_with_gatelock(tmp_path: Path):
    """earned_time signed them (the tutor); gatelock's HMAC is the same bytes."""
    key = _key(tmp_path)
    for row in _rows():
        body = {k: v for k, v in row.items() if k != "hmac"}
        assert compute_entry_hmac(body, key_file=key) == row["hmac"]
        assert verify_entry_hmac(row, key_file=key)


def test_a_gatelock_signed_row_verifies_with_earned_time(tmp_path: Path):
    """The other direction: what the guard signs, the tutor's library accepts."""
    key = _key(tmp_path)
    body = {k: v for k, v in DOC["ledger"]["entries"][0].items() if k != "hmac"}
    signed = {**body, "hmac": compute_entry_hmac(body, key_file=key)}

    assert earned_time.verified(signed, DOC["key"].encode())
    assert signed["hmac"] == earned_time.entry_signature(body, DOC["key"].encode())


def test_only_the_teaching_row_pays_its_module(tmp_path: Path):
    """C1: the review row has no ``module``; the teaching row pays 12."""
    _install("ledger.json", DOC["ledger"])
    teach = DOC["ledger"]["entries"][0]
    day = datetime.fromtimestamp(teach["detail"]["ended_at"]).astimezone().date()

    rows = signed_rows("ledger.json", key_file=_key(tmp_path))

    assert rows is not None
    assert len(rows) == len(DOC["ledger"]["entries"])
    assert (
        teaching_minutes(rows, ALGO, (MODULE,), day=day) == teach["detail"]["minutes"]
    )
    assert teaching_minutes(rows, ALGO, ("bits",), day=day) == 0


def test_the_latest_c2_flip_is_the_modules_state(tmp_path: Path):
    """C2: two flips of one module, the later (done) one wins."""
    _install("module_state.json", DOC["module_state"])

    rows = signed_rows("module_state.json", key_file=_key(tmp_path))

    assert rows is not None
    last = DOC["module_state"]["entries"][-1]["detail"]
    assert module_states(rows) == {(ALGO, MODULE): (last["at"], True)}
    assert [row["entry_id"] for row in rows] == [
        f"state:{ALGO}:{MODULE}:1",
        f"state:{ALGO}:{MODULE}:2",
    ]
