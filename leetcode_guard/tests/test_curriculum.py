"""The curriculum order: which theory block a problem is served in."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _curriculum
from leetcode_guard._curriculum import (
    Blocks,
    Curriculum,
    Theory,
    load_curriculum,
    parse_curriculum,
)
from leetcode_guard._problem import rank_pool
from leetcode_guard.tests._pool_fixtures import resolve_offline
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
            "tutor": {"subject": "algo", "modules": ["bit-manipulation"]},
        },
        {"id": "js", "tags": [], "untagged": True},
    ],
}


def curriculum() -> Curriculum:
    """The three-unit curriculum every test here orders by."""
    parsed = parse_curriculum(DOCUMENT)
    assert parsed is not None
    return parsed


def blocks(*theory: Theory) -> Blocks:
    """The curriculum with each unit's theory state; none mapped by default."""
    return Blocks(curriculum=curriculum(), theory=theory or (Theory.NONE,) * 3)


def test_ordering_follows_the_curriculum():
    """An earlier block is served first, whatever its acceptance rate."""
    problems = [
        make("bits-easy", ac_rate=99.0, topics=["bit-manipulation"]),
        make("scan-hard", ac_rate=40.0, topics=["array"]),
        make("scan-easy", ac_rate=80.0, topics=["string"]),
    ]

    ranked = rank_pool(problems, block=blocks().key)

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

    ranked = rank_pool(problems, block=blocks().key)

    assert [p.title_slug for p in ranked] == ["easy-bits", "medium-scan"]


def test_a_unit_keeps_its_tutor_module():
    """The theory lookup needs the subject and module a unit points at."""
    units = curriculum().units

    assert (units[1].subject, units[1].modules) == ("algo", ("bit-manipulation",))
    assert (units[0].subject, units[0].modules) == ("", ())


def test_a_missing_file_keeps_the_acceptance_order(tmp_path: Path):
    """No curriculum is not an error: the list falls back to the old order."""
    assert load_curriculum(tmp_path / "absent.json") is None
    assert load_curriculum() is None


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
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": 1, "modules": ["m"]}}]},
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": "s"}}]},
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": "s", "modules": "m"}}]},
        {
            "units": [
                {"id": "a", "tags": [], "tutor": {"subject": "s", "modules": [""]}}
            ]
        },
        {"units": [{"id": "a", "tags": [], "tutor": {"subject": "s", "modules": []}}]},
        {"units": [{"id": "a", "tags": ["x"]}], "claim_order": "a"},
        {"units": [{"id": "a", "tags": ["x"]}], "claim_order": ["a", "a"]},
        {"units": [{"id": "a", "tags": ["x"]}], "claim_order": ["b"]},
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
    """The real file: every unit distinct, the smallest unit taught first."""
    shipped = load_curriculum(_curriculum.SHIPPED_CURRICULUM_FILE)

    assert shipped is not None
    assert shipped.units[0].unit_id == "prefix-sums"
    assert shipped.unit_index(("array",)) == len(shipped.units) - 1
    assert shipped.unit_index(("array", "bit-manipulation")) < len(shipped.units) - 1
    assert shipped.unit_index(()) < len(shipped.units)


def test_the_suggestion_list_is_served_in_curriculum_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """End to end through the resolver, the path the lock and MCP both use."""
    curriculum_file = tmp_path / "curriculum.json"
    curriculum_file.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", curriculum_file)
    resolution = resolve_offline(
        tmp_path,
        make("bits-easy", ac_rate=99.0, topics=["bit-manipulation"]),
        make("scan-hard", ac_rate=40.0, topics=["array"]),
    )

    assert [p.title_slug for p in resolution.problems] == ["scan-hard", "bits-easy"]


def test_a_waiting_block_is_pushed_below_the_taught_ones():
    """Theory not taught yet: the block stays on the list, under the rest."""
    problems = [
        make("scan", ac_rate=10.0, topics=["array"]),
        make("bits", ac_rate=99.0, topics=["bit-manipulation"]),
        make("js", ac_rate=50.0),
    ]
    state = blocks(Theory.PENDING, Theory.DONE, Theory.UNKNOWN)

    ranked = rank_pool(problems, block=state.key)

    assert [p.title_slug for p in ranked] == ["bits", "scan", "js"]
    assert [state.waits(p) for p in ranked] == [False, True, True]
    assert [state.unit_id(p) for p in ranked] == ["bits", "scans", "js"]


def test_the_claim_order_settles_membership_not_the_teaching_order():
    """Taught first, claimed first: an array+bits problem still waits for bits."""
    scans = {"id": "scans", "tags": ["array", "string"]}
    bits = {"id": "bits", "tags": ["bit-manipulation"]}
    js = {"id": "js", "tags": [], "untagged": True}
    parsed = parse_curriculum(
        {"units": [bits, scans, js], "claim_order": ["scans", "bits", "js"]}
    )

    assert parsed is not None
    assert parsed.unit_index(("array", "bit-manipulation")) == 0
    assert parsed.unit_index(("array",)) == 1


def test_a_problem_no_unit_claims_never_waits():
    """Nothing teaches it, so there is nothing to wait for and no block id."""
    stray = make("stray", topics=["union-find"])
    state = blocks(Theory.PENDING, Theory.PENDING, Theory.PENDING)

    assert state.theory_of(stray) is Theory.NONE
    assert not state.waits(stray)
    assert state.unit_id(stray) == ""
