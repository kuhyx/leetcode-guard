"""C6: the signed trigger of the tutor's post-mortem (``unit_finish.json``)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard import _constants, _curriculum, _unit_finish
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase import PhaseState
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard.tests._finish_fixtures import NOW, solved_a1
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import world
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_phase import DOCUMENT as THREE_UNITS
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

AT_B = PhaseState("b", "theory", ALGO, ("b1", "b2"), solved=0, total=1)


def _rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def _record(ledger: Ledger, key: Path, state: PhaseState = AT_B) -> list[Any]:
    return _unit_finish.record_finishes(ledger, state, now=NOW, key_file=key)


def _solved(key: Path, *slugs: str) -> Ledger:
    ledger = Ledger()
    solved_a1(ledger, key)
    for n, slug in enumerate(slugs):
        sub = submission(str(10 + n), slug)
        append(ledger, [credit_entry(sub, day=NOW.date(), now=NOW, key_file=key)])
    return ledger


def _pool(*problems: tuple[str, str]) -> None:
    found = tuple(make(slug, topics=[tag]) for slug, tag in problems)
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=found, fetched_at=0.0, complete=True),
    )


def test_a_finished_unit_gets_one_signed_row_until_its_solves_change(
    tmp_path, monkeypatch, hmac_key: Path
):
    """Row 1 names a's solves; the same solves write nothing; a new one is row 2."""
    world(tmp_path, monkeypatch)
    ledger = _solved(hmac_key)

    made = _record(ledger, hmac_key)

    assert [r["entry_id"] for r in made] == ["finish:a:1"]
    assert made[0]["detail"] == {
        "unit": "a",
        "subject": ALGO,
        "modules": ["a"],
        "at": NOW.timestamp(),
        "solves": ["a1"],
    }
    assert (made[0]["kind"], made[0]["day"]) == ("unit_finish", str(NOW.date()))
    saved = _rows(_unit_finish.FINISH_FILE)
    assert saved == made
    assert verify_entry_hmac(saved[0], key_file=hmac_key)
    assert _record(ledger, hmac_key) == []

    _pool(("a1", "x"), ("a9", "x"), ("q1", "nowhere"))
    more = _solved(hmac_key, "a9", "q1")
    again = _record(more, hmac_key)

    assert [r["entry_id"] for r in again] == ["finish:a:2"]
    assert again[0]["detail"]["solves"] == ["a1", "a9"]
    assert len(_rows(_unit_finish.FINISH_FILE)) == 2


def test_every_mapped_unit_is_finished_when_the_machine_is_past_them(
    tmp_path, monkeypatch, hmac_key: Path
):
    """No current unit: a and b both get a row (b with no solve)."""
    world(tmp_path, monkeypatch)
    done = PhaseState("", "none", "", ())

    made = _record(_solved(hmac_key), hmac_key, done)

    assert [r["entry_id"] for r in made] == ["finish:a:1", "finish:b:1"]
    assert made[1]["detail"]["solves"] == []


def test_nothing_is_written_while_the_first_unit_is_current(
    tmp_path, monkeypatch, hmac_key: Path
):
    """THEORY(a), an unknown unit, or no curriculum: no finished unit, no file."""
    world(tmp_path, monkeypatch)
    at_a = PhaseState("a", "theory", ALGO, ("a",))
    gone = PhaseState("zzz", "theory", ALGO, ("z",))

    assert _record(_solved(hmac_key), hmac_key, at_a) == []
    assert _record(_solved(hmac_key), hmac_key, gone) == []
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", tmp_path / "missing.json")
    assert _record(_solved(hmac_key), hmac_key) == []
    assert not _unit_finish.FINISH_FILE.exists()


def test_an_unsigned_pool_or_no_key_writes_nothing(
    tmp_path, monkeypatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Cannot check the claims, or cannot sign: no row, one warning."""
    world(tmp_path, monkeypatch)
    monkeypatch.setattr(_unit_finish, "read_cache", lambda *_a, **_k: None)
    with caplog.at_level(logging.WARNING):
        assert _record(_solved(hmac_key), hmac_key) == []
    assert "no signed problem pool" in caplog.text


def test_no_signing_key_writes_nothing(tmp_path, monkeypatch, hmac_key: Path):
    """A row that cannot be signed is not written, and nothing else is."""
    world(tmp_path, monkeypatch)
    monkeypatch.setattr(_unit_finish, "compute_entry_hmac", lambda *_a, **_k: None)

    assert _record(_solved(hmac_key), hmac_key) == []
    assert not _unit_finish.FINISH_FILE.exists()


def test_a_forged_or_broken_row_is_dropped_and_rewritten(
    tmp_path, monkeypatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """An edited row fails its signature: dropped, logged, and a=1 is written anew."""
    world(tmp_path, monkeypatch)
    path = _unit_finish.FINISH_FILE
    forged = {"entry_id": "finish:a:1", "detail": {"solves": ["a1"]}, "hmac": "x"}
    path.write_text(json.dumps({"entries": [forged, "junk"]}), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        made = _record(_solved(hmac_key), hmac_key)

    assert [r["entry_id"] for r in made] == ["finish:a:1"]
    assert "2 unverified rows dropped" in caplog.text
    assert _rows(path) == made

    path.write_text("[1]", encoding="utf-8")
    assert [r["entry_id"] for r in _record(_solved(hmac_key), hmac_key)] == [
        "finish:a:1"
    ]


def test_a_raising_check_drops_a_row_and_a_bad_detail_is_rewritten(
    tmp_path, monkeypatch, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """A check that raises distrusts the row; a signed row with no detail is stale."""
    world(tmp_path, monkeypatch)
    path = _unit_finish.FINISH_FILE
    odd = {"kind": "unit_finish", "entry_id": "finish:a:1", "detail": "x"}
    odd["hmac"] = str(compute_entry_hmac(odd, key_file=hmac_key))
    path.write_text(json.dumps({"entries": [odd]}), encoding="utf-8")

    made = _record(_solved(hmac_key), hmac_key)

    assert [r["entry_id"] for r in made] == ["finish:a:2"]

    def boom(*_a: object, **_k: object) -> bool:
        raise ValueError

    monkeypatch.setattr(_unit_finish, "verify_entry_hmac", boom)
    with caplog.at_level(logging.WARNING):
        again = _record(_solved(hmac_key), hmac_key)

    assert [r["entry_id"] for r in again] == ["finish:a:1"]
    assert "signature check raised" in caplog.text


def _preview(ledger: Ledger, key: Path, unit: str = "b") -> object:
    return _unit_finish.write_preview(ledger, unit, now=NOW, key_file=key)


def test_a_preview_is_one_signed_row_for_any_mapped_unit(
    tmp_path, monkeypatch, hmac_key: Path
):
    """Unfinished b still gets a row (kind unit_preview); the file holds only it."""
    world(tmp_path, monkeypatch)

    made = _preview(_solved(hmac_key), hmac_key)

    assert isinstance(made, dict)
    assert (made["kind"], made["entry_id"]) == ("unit_preview", "finish:b:1")
    assert _rows(_unit_finish.PREVIEW_FILE) == [made]
    assert _preview(_solved(hmac_key), hmac_key, "a") is not None
    assert [r["detail"]["unit"] for r in _rows(_unit_finish.PREVIEW_FILE)] == ["a"]


def test_a_preview_is_refused_without_theory_a_pool_or_a_key(
    tmp_path, monkeypatch, hmac_key: Path
):
    """An unmapped or unknown unit, an unsigned pool, no key: ``None``, no file."""
    world(tmp_path, monkeypatch)
    path = tmp_path / "three.json"
    path.write_text(json.dumps(THREE_UNITS), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", path)
    ledger = _solved(hmac_key)

    assert _preview(ledger, hmac_key, "free") is None
    assert _preview(ledger, hmac_key, "nope") is None
    with monkeypatch.context() as local:
        local.setattr(_unit_finish, "read_cache", lambda *_a, **_k: None)
        assert _preview(ledger, hmac_key) is None
    with monkeypatch.context() as local:
        local.setattr(_unit_finish, "compute_entry_hmac", lambda *_a, **_k: None)
        assert _preview(ledger, hmac_key) is None
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", tmp_path / "missing.json")
    assert _preview(ledger, hmac_key) is None
    assert not _unit_finish.PREVIEW_FILE.exists()
