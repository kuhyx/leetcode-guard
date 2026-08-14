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


def test_a_null_status_is_never_treated_as_solved():
    """A null is what a signed-in user gets for a problem never attempted.

    Verified against the live API on 2026-08-14: with a working session,
    solved problems return "ac", problems with a failed submission return
    "notac", and problems never opened return null. So a null must not count
    as solved -- but it is a real answer, not silence.
    """
    post = fake_post(status_result("two-sum", None))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.solved == frozenset()
    assert evidence.checked == 1
    assert evidence.recognised == 0
    assert evidence.complete


def test_an_all_null_sweep_is_not_mistaken_for_a_dead_session():
    """The bug a live session exposed.

    `signed_in` first keyed on "some status came back non-null", which is
    exactly what a signed-in user browsing ten never-opened problems does NOT
    produce. The lock then announced it could not check solved-state while
    holding a freshly verified cookie, and abandoned the rest of the sweep.
    """
    post = fake_post(status_result("a", None))

    evidence = check_solved(post, ["a", "b", "c"])

    assert evidence.signed_in
    assert evidence.checked == 3
    assert evidence.recognised == 0


def test_a_missing_envelope_is_silence_not_an_answer():
    """Distinct from a null status: nothing came back to read at all."""
    post = fake_post(GraphQLResult(data={}))

    evidence = check_solved(post, ["two-sum"])

    assert evidence.checked == 0
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
