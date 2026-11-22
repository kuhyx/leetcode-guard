"""``GET /api/theory`` counts review minutes with lesson minutes (kuhy 2026-11-22)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _tutor_signed
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests._tutor_fixtures import review_row, write_tutor
from leetcode_guard.tests.test_unit_view import solved
from leetcode_guard.tests.test_web_theory import NOW, theory

if TYPE_CHECKING:
    from pathlib import Path


def test_the_bar_shows_lesson_plus_free_review_minutes(
    tmp_path, monkeypatch, hmac_key: Path
):
    """THEORY(a): 3 lesson + 4 review minutes read 7 of 12, as the mint will count."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 3))
    reviews = [review_row(f"r-m{i}", 1, ended=NOW, key_file=hmac_key) for i in range(4)]
    rows = json.loads((_tutor_signed.TUTOR_DIR / "ledger.json").read_text("utf-8"))
    write_tutor("ledger.json", [*rows["entries"], *reviews])

    block = theory(hmac_key)

    assert (block["minutes_today"], block["minutes_into_credit"]) == (7, 7)


def test_in_none_reviews_still_fill_the_bar(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Every unit finished: 5 review minutes show 5 of 12."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1", "b1-easy")
    write_tutor(
        "ledger.json",
        [review_row(f"r-m{i}", 1, ended=NOW, key_file=hmac_key) for i in range(5)],
    )

    block = theory(hmac_key)

    assert (block["phase"], block["minutes_today"]) == ("none", 5)
    assert block["minutes_into_credit"] == 5
