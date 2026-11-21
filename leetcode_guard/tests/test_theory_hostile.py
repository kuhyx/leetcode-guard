"""Hostile and half-written tutor files: the reader fails open, never raises.

The tutor's log is appended by a live server, so a reader can see any prefix of
it, a multibyte character cut in two included. A lock that dies while reading
display-only files never arms, so every case below must end as a state (DONE
from the lines that did parse, or UNKNOWN) plus exactly one warning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _pool_resolve
from leetcode_guard._curriculum import Theory
from leetcode_guard.tests._pool_fixtures import resolve_offline
from leetcode_guard.tests.test_theory import states as theory_states
from leetcode_guard.tests.test_theory import taught, tutor_dir
from leetcode_guard.tests.test_theory_surface import (
    POOL,
    TREE_CARDS,
    TREES_TAUGHT,
    use,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

BITS_DONE = (taught("algo", "xor"), taught("algo", "masks"))
DEEP = "[" * 100_000
POLISH_L = "ł".encode()


def warnings_about(caplog: pytest.LogCaptureFixture, word: str) -> list[str]:
    """The WARNING-or-above messages mentioning ``word``."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelname != "INFO" and word in record.getMessage()
    ]


def append(root: Path, raw: bytes) -> None:
    """Append raw bytes to the tutor log, the way a cut write would."""
    with (root / "log.jsonl").open("ab") as log:
        log.write(raw)


def test_a_torn_multibyte_tail_keeps_every_line_before_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The tutor was mid-write of a Polish letter: one of its two bytes is on disk."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    append(root, b'{"k": "note", "text": "' + POLISH_L[:1])

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.DONE

    assert len(warnings_about(caplog, "torn line(s)")) == 1


def test_a_stray_ff_byte_costs_its_line_not_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """0xff is never valid UTF-8; the lines around it still count."""
    root = tutor_dir(tmp_path, taught("algo", "xor"))
    append(root, b"\xff\xfe\x80\n")
    append(root, b'{"k":"taught","s":"algo","c":"masks"}\n')

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.DONE

    assert len(warnings_about(caplog, "torn line(s)")) == 1


def test_many_bad_lines_warn_once_per_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A log full of garbage is one warning, not one per line."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    append(root, b"\xff\n{\n[1,\n" * 50)

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.DONE

    assert len(warnings_about(caplog, "torn line(s)")) == 1


def test_a_deeply_nested_log_line_is_skipped_like_a_torn_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """100k open brackets overflow the JSON parser's recursion limit."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    append(root, DEEP.encode() + b"\n")

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.DONE

    assert len(warnings_about(caplog, "torn line(s)")) == 1


def test_a_deeply_nested_cards_file_is_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The same overflow in ``cards.json`` reads as "cannot check"."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    (root / "subjects" / "algo" / "cards.json").write_text(DEEP, encoding="utf-8")

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, "algo/cards.json")) == 1


def test_an_undecodable_cards_file_is_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """Bytes that are not UTF-8 in the cards file are a ValueError, not a crash."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    (root / "subjects" / "algo" / "cards.json").write_bytes(b'{"x": "\xff"}')

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, "algo/cards.json")) == 1


def test_a_resolver_survives_a_raising_theory_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """The last-resort fence: whatever ``load_blocks`` does, the pool comes back
    in the old acceptance order, with one warning naming the exception."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path, *TREES_TAUGHT, cards=TREE_CARDS))
    theory_order = resolve_offline(tmp_path, *POOL)
    assert [p.title_slug for p in theory_order.problems] == ["tree-walk", "bit-trick"]

    def boom() -> object:
        return b"\xff".decode("utf-8")

    monkeypatch.setattr(_pool_resolve, "load_blocks", boom)
    with caplog.at_level("WARNING"):
        fenced = resolve_offline(tmp_path, *POOL)

    assert fenced.blocks is None
    assert [p.title_slug for p in fenced.problems] == ["bit-trick", "tree-walk"]
    assert len(warnings_about(caplog, "UnicodeDecodeError")) == 1
