"""The tutor's ``leetcode_theory`` rows pay theory minutes exactly like ``credit`` rows.

From 2026-11-23 the tutor writes a minute on a LeetCode subject as
``kind: "leetcode_theory"``, so earned_time's tutor earner stops paying it
(the double pay kuhy reported). ``tutor_measured_2026-11-23.json`` holds rows
written by the tutor's own ``tutor.credit.build_row`` at eaa69d6 (generator:
``~/data/claude-scratch/lc-kind-2026-11-23/gen_lc_kind_fixture.py``), never
touched by guard code: a LeetCode lesson row, a LeetCode review row and an
ungated subject's ``credit`` row, signed with the fixture key in the file.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from leetcode_guard import _tutor_signed
from leetcode_guard._tutor_minutes import MINUTE_KINDS, review_minutes, teaching_minutes
from leetcode_guard._tutor_signed import signed_rows
from leetcode_guard.tests._tutor_fixtures import ALGO, signed

GOLDEN = Path(__file__).with_name("tutor_measured_2026-11-23.json")
DOC = json.loads(GOLDEN.read_text(encoding="utf-8"))
LESSON, REVIEW, UNGATED = DOC["ledger"]["entries"]
MODULE = "prefix-sums"
DAY = datetime.fromtimestamp(LESSON["detail"]["ended_at"]).astimezone().date()


def _key(tmp_path: Path) -> Path:
    path = tmp_path / "tutor.key"
    path.write_bytes(DOC["key"].encode())
    return path


def _read(tmp_path: Path, rows: list[object]) -> list[dict[str, object]]:
    """``rows`` written as the tutor's ledger and read back through verification."""
    _tutor_signed.TUTOR_DIR.mkdir(parents=True, exist_ok=True)
    path = _tutor_signed.TUTOR_DIR / "ledger.json"
    path.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    found = signed_rows("ledger.json", key_file=_key(tmp_path))
    assert found is not None
    return found


def _as_credit(row: dict[str, object], key_file: Path) -> dict[str, object]:
    """``row`` re-signed as ``kind: "credit"``, the shape before 2026-11-23."""
    body = {k: v for k, v in row.items() if k != "hmac"} | {"kind": "credit"}
    return signed(body, key_file)


def test_the_tutor_writes_gated_minutes_as_leetcode_theory():
    """The golden rows: LeetCode minutes are the new kind, others stay credit."""
    assert [r["kind"] for r in (LESSON, REVIEW, UNGATED)] == [
        "leetcode_theory",
        "leetcode_theory",
        "credit",
    ]
    assert frozenset({"credit", "leetcode_theory"}) == MINUTE_KINDS


def test_a_leetcode_theory_lesson_pays_like_a_credit_row(tmp_path: Path):
    """A lesson row pays the same minutes in either kind."""
    new = _read(tmp_path, [LESSON])
    old = _read(tmp_path, [_as_credit(LESSON, _key(tmp_path))])
    paid = teaching_minutes(new, ALGO, (MODULE,), day=DAY)
    assert paid == LESSON["detail"]["minutes"] == 12
    assert teaching_minutes(old, ALGO, (MODULE,), day=DAY) == paid


def test_a_leetcode_theory_review_pays_review_minutes(tmp_path: Path):
    """A review row pays review minutes, never lesson minutes."""
    rows = _read(tmp_path, [REVIEW])
    assert review_minutes(rows, {(ALGO, MODULE)}, day=DAY) == 3
    assert teaching_minutes(rows, ALGO, (MODULE,), day=DAY) == 0


def test_a_row_both_kinds_repeat_pays_once(tmp_path: Path):
    """A twin of one ``entry_id`` in the other kind pays its smallest count once."""
    rows = _read(tmp_path, [LESSON, _as_credit(LESSON, _key(tmp_path))])
    assert teaching_minutes(rows, ALGO, (MODULE,), day=DAY) == 12


def test_an_unsigned_or_edited_leetcode_theory_row_pays_nothing(tmp_path: Path):
    """Verification drops a forged new-kind row before it is counted."""
    unsigned = {k: v for k, v in LESSON.items() if k != "hmac"}
    edited = LESSON | {"detail": LESSON["detail"] | {"minutes": 120}}
    rows = _read(tmp_path, [unsigned, edited])
    assert rows == []
    assert teaching_minutes(rows, ALGO, (MODULE,), day=DAY) == 0


def test_a_signed_row_of_another_kind_pays_nothing(tmp_path: Path):
    """Only the two minute kinds pay; a signed row of any other kind does not."""
    body = {k: v for k, v in LESSON.items() if k != "hmac"} | {"kind": "theory_phase"}
    rows = _read(tmp_path, [signed(body, _key(tmp_path))])
    assert len(rows) == 1
    assert teaching_minutes(rows, ALGO, (MODULE,), day=DAY) == 0
