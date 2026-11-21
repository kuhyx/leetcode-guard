"""Theory state as kuhy sees it: row order, the pencil mark, the MCP fields.

Continued from :mod:`leetcode_guard.tests.test_theory`, split for the 250-line cap.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _curriculum, _mcp, _theory
from leetcode_guard import _glyphs as g
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._theory import load_blocks
from leetcode_guard._viewmodel import build_problem_lines
from leetcode_guard.tests._pool_fixtures import resolve_offline
from leetcode_guard.tests.test_problem import make
from leetcode_guard.tests.test_theory import CARDS, DOCUMENT, taught, tutor_dir

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from leetcode_guard._pool_resolve import PoolResolution

TREE_CARDS = {**CARDS, "levels": {"module": "bfs", "suspended": False}}
TREES_TAUGHT = (taught("algo", "preorder"), taught("algo", "levels"))
POOL = (
    make("bit-trick", ac_rate=99.0, topics=["bit"]),
    make("tree-walk", ac_rate=50.0, topics=["tree"]),
)


def use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Put ``DOCUMENT`` and the tutor dir ``root`` in force for this test."""
    curriculum_file = tmp_path / "curriculum.json"
    curriculum_file.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", curriculum_file)
    monkeypatch.setattr(_theory, "TUTOR_DATA_DIR", root)


def resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root: Path
) -> PoolResolution:
    """Resolve the two-problem pool under ``DOCUMENT`` and the tutor dir ``root``."""
    use(tmp_path, monkeypatch, root)
    return resolve_offline(tmp_path, *POOL)


def test_teaching_a_module_unmarks_its_rows_and_moves_them_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Both sides of the feature, through the resolver and the view model:
    untaught, every row carries the mark; teach the tree modules and their rows
    lose the mark and overtake the block still waiting."""
    before = resolve(tmp_path, monkeypatch, tutor_dir(tmp_path / "before"))
    lines, _ = build_problem_lines(before, limit=8)

    assert [line.slug for line in lines] == ["bit-trick", "tree-walk"]
    assert all(line.mark.startswith(g.THEORY_PENDING) for line in lines)

    root = tutor_dir(tmp_path / "after", *TREES_TAUGHT, cards=TREE_CARDS)
    after = resolve(tmp_path, monkeypatch, root)
    lines, _ = build_problem_lines(after, limit=8)

    assert [line.slug for line in lines] == ["tree-walk", "bit-trick"]
    assert lines[0].mark == f"{g.CREDIT}  50%"
    assert lines[1].mark == f"{g.THEORY_PENDING}  {g.CREDIT}  99%"


def test_mcp_names_each_block_and_its_theory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    """A Claude session can see which block is up and whether it was taught."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path, *TREES_TAUGHT, cards=TREE_CARDS))
    write_cache(
        data_dir / "pool_cache.json",
        CachedPool(problems=POOL, fetched_at=2**31, complete=True),
    )

    rows = _mcp.get_suggested_problems()

    assert [(row["unit"], row["theory"]) for row in rows] == [
        ("trees", "done"),
        ("bits", "pending"),
    ]


def test_no_curriculum_means_no_blocks():
    """The suite default: no curriculum file, so the old order and no marks."""
    assert load_blocks() is None
