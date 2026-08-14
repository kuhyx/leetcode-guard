"""Tests for the live solved-state check.

The invariant under test throughout: a live check may only ever *add* to what
is known. It can confirm a solve; it can never assert one has not happened,
because the payload that says "not solved" and the payload that says "I do not
know who you are" are the same null.
"""

from __future__ import annotations

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._live_solved import LiveSolved, check_solved, parse_status
from leetcode_guard.tests._net_fixtures import fake_post, status_result


def test_an_accepted_status_is_reported_as_solved():
    post = fake_post(status_result("two-sum", "ac"))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.solved == frozenset({"two-sum"})
    assert evidence.checked == 1
    assert evidence.attempted == 1
    assert evidence.complete
    assert evidence.signed_in


def test_an_unsolved_status_is_checked_but_not_solved():
    post = fake_post(status_result("two-sum", "notac"))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.solved == frozenset()
    assert evidence.checked == 1
    assert evidence.signed_in


def test_a_null_status_is_not_evidence_of_anything():
    """The failure this whole module exists for.

    An expired session returns HTTP 200 with a well-formed payload whose status
    is null. Counting that as "checked, not solved" is how a solved problem
    ends up back at the top of the suggestion list.
    """
    post = fake_post(status_result("two-sum", None))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.solved == frozenset()
    assert evidence.checked == 0
    assert evidence.attempted == 1
    assert not evidence.signed_in
    assert not evidence.complete


def test_a_transport_error_leaves_the_problem_unchecked():
    post = fake_post(GraphQLResult(transport_error="down"))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.checked == 0
    assert not evidence.signed_in


def test_a_graphql_error_leaves_the_problem_unchecked():
    post = fake_post(GraphQLResult(errors=("nope",)))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.checked == 0
    assert not evidence.signed_in


def test_one_failure_does_not_discard_the_others():
    post = fake_post(
        status_result("solved", "ac"),
        GraphQLResult(transport_error="down"),
        status_result("open", "notac"),
    )

    evidence = check_solved(post, ["solved", "broken", "open"])

    assert evidence.solved == frozenset({"solved"})
    assert evidence.checked == 2
    assert evidence.attempted == 3
    assert not evidence.complete
    assert evidence.signed_in


def test_checking_nothing_asks_nothing():
    post = fake_post(status_result("x", "ac"))

    evidence = check_solved(post, [])

    assert evidence == LiveSolved()
    assert post.calls == []


def test_one_request_is_sent_per_problem():
    post = fake_post(status_result("a", "notac"))

    check_solved(post, ["a", "b", "c"])

    assert [call[1]["titleSlug"] for call in post.calls] == ["a", "b", "c"]


def test_parse_status_rejects_unusable_payloads():
    assert parse_status("not-an-object") is None
    assert parse_status({}) is None
    assert parse_status({"question": "not-an-object"}) is None
    assert parse_status({"question": {}}) is None
    assert parse_status({"question": {"status": 7}}) is None
    assert parse_status({"question": {"status": ""}}) is None
    assert parse_status({"question": {"status": "ac"}}) == "ac"
