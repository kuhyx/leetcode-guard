"""``_theory.module_cards``: taught / live card counts per module, display only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _theory
from leetcode_guard._theory import module_cards
from leetcode_guard.tests.test_theory import taught, tutor_dir

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

MODULES = ("bits", "dfs", "bfs")


def test_counts_live_cards_and_the_taught_ones_per_module(tmp_path: Path):
    """Suspended cards never count; a module with no cards reads (0, 0)."""
    root = tutor_dir(tmp_path, taught("algo", "xor"), taught("algo", "retired"))

    assert module_cards("algo", MODULES, root) == {
        "bits": (1, 2),
        "dfs": (0, 1),
        "bfs": (0, 0),
    }


def test_an_untaught_event_takes_the_card_back(tmp_path: Path):
    """The log folds in file order, like the tutor's own."""
    untaught = {**taught("algo", "xor"), "k": "untaught"}
    root = tutor_dir(tmp_path, taught("algo", "xor"), untaught)

    assert module_cards("algo", ("bits",), root) == {"bits": (0, 2)}


def test_an_unreadable_log_is_none(tmp_path: Path):
    """Cannot check is never "nothing taught"."""
    root = tutor_dir(tmp_path)
    (root / "log.jsonl").unlink()

    assert module_cards("algo", MODULES, root) is None


def test_unreadable_cards_are_none(tmp_path: Path):
    """A cards file that is not an object: None, not zero cards."""
    root = tutor_dir(tmp_path, cards=[])

    assert module_cards("algo", MODULES, root) is None


def test_the_default_root_is_read_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``root=None`` means :data:`_theory.TUTOR_DATA_DIR` as it is now."""
    root = tutor_dir(tmp_path, taught("algo", "preorder"))
    monkeypatch.setattr(_theory, "TUTOR_DATA_DIR", root)

    assert module_cards("algo", ("dfs",)) == {"dfs": (1, 1)}
