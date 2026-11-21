"""The curriculum order: which theory block a problem is served in."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _curriculum
from leetcode_guard._curriculum import (
    Curriculum,
    block_order,
    load_curriculum,
    parse_curriculum,
)
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._problem import rank_pool
from leetcode_guard.tests.test_pool_resolve import SIGNED_OUT, path_of
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

DOCUMENT = {
    "version": 1,
    "units": [
        {"id": "scans", "tags": ["array", "string"]},
        {
            "id": "bits",
            "tags": ["bit-manipulation"],
            "tutor": {"subject": "algo", "module": "bit-manipulation"},
        },
        {"id": "js", "tags": [], "untagged": True},
    ],
}


def curriculum() -> Curriculum:
    """The three-unit curriculum every test here orders by."""
    parsed = parse_curriculum(DOCUMENT)
    assert parsed is not None
    return parsed


def test_ordering_follows_the_curriculum():
    """An earlier block is served first, whatever its acceptance rate."""
    problems = [
        make("bits-easy", ac_rate=99.0, topics=["bit-manipulation"]),
        make("scan-hard", ac_rate=40.0, topics=["array"]),
        make("scan-easy", ac_rate=80.0, topics=["string"]),
    ]

    ranked = rank_pool(problems, block=curriculum().unit_index_of)

    assert [p.title_slug for p in ranked] == ["scan-easy", "scan-hard", "bits-easy"]


def test_a_problem_belongs_to_the_latest_unit_among_its_tags():
    """An array problem that also needs a bit trick waits for the bit block."""
    assert curriculum().unit_index(("array", "bit-manipulation")) == 1


def test_an_unmapped_tag_sorts_after_every_unit():
    """A tag no unit claims must not jump the queue."""
    assert curriculum().unit_index(("union-find",)) == 3
    assert curriculum().unit_index(("array", "union-find")) == 0


def test_an_untagged_problem_goes_to_the_untagged_unit():
    """LeetCode's JavaScript problems carry no tags at all."""
    assert curriculum().unit_index(()) == 2


def test_an_untagged_problem_without_such_a_unit_sorts_last():
    """No unit claims the untagged ones: they go after every block."""
    parsed = parse_curriculum({"units": [{"id": "scans", "tags": ["array"]}]})

    assert parsed is not None
    assert parsed.unit_index(()) == 1


def test_difficulty_still_outranks_the_curriculum():
    """Easiest first is the user's rule; blocks order problems inside it."""
    problems = [
        make("medium-scan", difficulty="Medium", topics=["array"]),
        make("easy-bits", difficulty="Easy", topics=["bit-manipulation"]),
    ]

    ranked = rank_pool(problems, block=curriculum().unit_index_of)

    assert [p.title_slug for p in ranked] == ["easy-bits", "medium-scan"]


def test_a_unit_keeps_its_tutor_module():
    """The theory lookup needs the subject and module a unit points at."""
    units = curriculum().units

    assert (units[1].subject, units[1].module) == ("algo", "bit-manipulation")
    assert (units[0].subject, units[0].module) == ("", "")


def test_a_missing_file_keeps_the_acceptance_order(tmp_path: Path):
    """No curriculum is not an error: the list falls back to the old order."""
    assert load_curriculum(tmp_path / "absent.json") is None
    assert block_order() is None


def test_a_broken_file_warns_and_keeps_the_acceptance_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A torn file must not take the suggestion list down with it."""
    path = tmp_path / "curriculum.json"
    path.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert load_curriculum(path) is None

    assert "curriculum" in caplog.text


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"units": "scans"},
        {"units": []},
        {"units": ["scans"]},
        {"units": [{"id": "", "tags": []}]},
        {"units": [{"id": 3, "tags": []}]},
        {"units": [{"id": "scans", "tags": "array"}]},
        {"units": [{"id": "scans", "tags": [3]}]},
        {"units": [{"id": "a", "tags": ["x"]}, {"id": "a", "tags": ["y"]}]},
        {"units": [{"id": "a", "tags": ["x"]}, {"id": "b", "tags": ["x"]}]},
        {"units": [{"id": "a", "tags": [], "tutor": "algo"}]},
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": 1, "module": "m"}}]},
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": "s"}}]},
    ],
)
def test_a_malformed_document_is_refused(
    document: object, caplog: pytest.LogCaptureFixture
):
    """Every shape error is refused whole and logged, never half-applied."""
    with caplog.at_level(logging.WARNING):
        assert parse_curriculum(document) is None

    assert caplog.text


def test_the_shipped_curriculum_parses():
    """The real file: every unit distinct, and the basics come first."""
    shipped = load_curriculum(_curriculum.SHIPPED_CURRICULUM_FILE)

    assert shipped is not None
    assert shipped.units[0].unit_id == "scans"
    assert shipped.unit_index(("array",)) == 0
    assert shipped.unit_index(("array", "bit-manipulation")) > 0
    assert shipped.unit_index(()) < len(shipped.units)


def test_the_suggestion_list_is_served_in_curriculum_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """End to end through the resolver, the path the lock and MCP both use."""
    curriculum_file = tmp_path / "curriculum.json"
    curriculum_file.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", curriculum_file)
    problems = (
        make("bits-easy", ac_rate=99.0, topics=["bit-manipulation"]),
        make("scan-hard", ac_rate=40.0, topics=["array"]),
    )
    write_cache(
        path_of(tmp_path), CachedPool(problems=problems, fetched_at=0.0, complete=True)
    )

    resolution = resolve_pool(
        None,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["scan-hard", "bits-easy"]
